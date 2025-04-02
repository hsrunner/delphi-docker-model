#!/usr/bin/env python3
"""
Delphi Method Simulation - A simplified implementation for character-based ethical analysis.
Modified to work with Docker and improved with Pythonic best practices.
"""
import requests
import json
import hjson
import time
import os
import re
import logging
import unicodedata
from enum import Enum
from functools import wraps, partial
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union, Callable, TypeVar, cast


# Type definitions for better type hinting
T = TypeVar('T')
JsonDict = Dict[str, Any]


# Enums for ratings and confidence levels
class Rating(Enum):
    """Rating scale for ethical positions."""
    STRONGLY_AGAINST = 1  # Strongly against waking them
    AGAINST = 2          # Against waking them
    SOMEWHAT_AGAINST = 3  # Somewhat against waking them
    NEUTRAL = 4          # Neutral/Uncertain
    SOMEWHAT_FAVOR = 5   # Somewhat favor waking them
    FAVOR = 6            # Favor waking them
    STRONGLY_FAVOR = 7   # Strongly favor waking them


class Confidence(Enum):
    """Confidence scale for assessments."""
    VERY_LOW = 1    # Not sure at all
    LOW = 2         # Not very sure
    MODERATE = 3    # Moderately sure
    HIGH = 4        # Pretty sure
    VERY_HIGH = 5   # Very sure


# Configuration dataclass for better type safety and structure
@dataclass
class DelphiConfig:
    """Configuration for the Delphi simulation."""
    # API settings
    api_host: str = field(default_factory=lambda: os.environ.get('API_HOST', 'localhost'))
    base_url: str = field(init=False)
    model: str = 'ai/gemma3'
    temperature: float = 0.7
    max_tokens: int = 2048
    api_timeout: int = 120
    api_max_retries: int = 3
    
    # Output settings
    output_dir: Path = field(default=Path('delphi_round1'))
    composite_json: Path = field(default=Path('round1_responses.json'))
    log_file: Path = field(default=Path('logs/delphi_process.log'))  # Changed this line
    debug_dir: Path = field(default=Path('debug_output'))
    
    # Response parameters
    question_count: int = 6
    rating_range: Tuple[int, int] = (1, 7)  # min, max
    confidence_range: Tuple[int, int] = (1, 5)  # min, max
    
    # Character list
    characters: List[str] = field(default_factory=lambda: [
        "bugs-bunny", "rick-sanchez", "stewie-griffin", "doraemon",
        "sandy-cheeks", "yoda", "bender", "stimpy", 
        "lisa-simpson", "twilight-sparkle"
    ])
    
    def __post_init__(self):
        """Initialize derived attributes after initialization."""
        self.base_url = f'http://{self.api_host}:12434/engines/llama.cpp/v1'
        
        # Create directories
        self.output_dir.mkdir(exist_ok=True)
        self.debug_dir.mkdir(exist_ok=True)
        self.log_file.parent.mkdir(exist_ok=True)


# Questions for the questionnaire (used in markdown generation)
QUESTIONS = [
    "What are the potential short-term and long-term consequences of reviving this ancient civilization?",
    "How might our intervention align with or violate the core principles of the Prime Directive?",
    "What ethical responsibility, if any, do we have toward a civilization that has been in stasis rather than naturally evolving?",
    "What alternative approaches could satisfy both our humanitarian impulses and our non-interference principles?",
    "How might we assess the potential impact on existing civilizations in this region if we proceed with revival?",
    "What criteria should we use to determine if this civilization deserves the same protection as other sentient species?"
]

# Rating descriptions for markdown generation
RATING_DESCRIPTIONS = {
    Rating.STRONGLY_AGAINST.value: "(Strongly against waking them)",
    Rating.AGAINST.value: "(Against waking them)",
    Rating.SOMEWHAT_AGAINST.value: "(Against waking them)",
    Rating.NEUTRAL.value: "(Neutral/Uncertain)",
    Rating.SOMEWHAT_FAVOR.value: "(Favor waking them)",
    Rating.FAVOR.value: "(Favor waking them)",
    Rating.STRONGLY_FAVOR.value: "(Strongly favor waking them)"
}

# Confidence descriptions for markdown generation
CONFIDENCE_DESCRIPTIONS = [
    "Not sure at all", "Not very sure", "Moderately sure", 
    "Pretty sure", "Very sure"
]

# Example JSON structure for the system prompt
EXAMPLE_JSON = """
{
  "responses": [
    {
      "question": 1,
      "rating": 5,
      "position_summary": "Brief summary of position for question 1.",
      "detailed_explanation": "Detailed explanation for question 1.",
      "confidence": 4
    },
    {
      "question": 2,
      "rating": 3,
      "position_summary": "Brief summary of position for question 2.",
      "detailed_explanation": "Detailed explanation for question 2.",
      "confidence": 5
    }
    ... and so on for all 6 questions
  ]
}
"""


def setup_logging(config: DelphiConfig) -> logging.Logger:
    """Set up logging with both console and file handlers."""
    logger = logging.getLogger('delphi')
    logger.setLevel(logging.INFO)
    
    # Create formatters
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', 
                                   datefmt='%Y-%m-%d %H:%M:%S')
    
    # Add console handler if not already present
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Add file handler
    file_handler = logging.FileHandler(config.log_file, mode='w')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def retry(max_retries: int = 3, backoff_factor: float = 2.0):
    """Retry decorator with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt == max_retries:
                        logger.error(f"All {max_retries} attempts failed. Last error: {str(e)}")
                        raise
                    wait_time = backoff_factor ** (attempt - 1)
                    logger.warning(f"Attempt {attempt} failed: {str(e)}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
            # This should never be reached due to the raise in the loop,
            # but it's needed for type checking
            raise last_error
        return wrapper
    return decorator


def find_file(name: str, extensions: Optional[List[str]] = None, 
              locations: Optional[List[str]] = None) -> Optional[Path]:
    """Find a file by name, with optional extensions and locations."""
    extensions = extensions or ['']  # Default to no extension
    locations = locations or ['', 'profiles/']  # Current dir and profiles dir
    
    # If name has a hyphen, also try the base name
    base_names = [name]
    if '-' in name:
        base_names.append(name.split('-')[0])
    
    # Try each combination
    for base_name in base_names:
        for location in locations:
            location_path = Path(location)
            for ext in extensions:
                path = location_path / f"{base_name}{ext}"
                if path.exists():
                    logger.info(f"Found file: {path}")
                    return path
    
    return None


def load_file(path: Path) -> Optional[str]:
    """Load file content from path using context manager."""
    try:
        return path.read_text(encoding='utf-8').strip()
    except Exception as e:
        logger.error(f"Error loading file {path}: {str(e)}")
        return None


def save_debug_file(config: DelphiConfig, character: str, 
                    content: str, suffix: str = "raw") -> None:
    """Save content to a debug file for inspection."""
    try:
        debug_path = config.debug_dir / f"{character}_{suffix}.txt"
        debug_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved debug file: {debug_path}")
    except Exception as e:
        logger.error(f"Error saving debug file for {character}: {str(e)}")


def normalize_text(text: str) -> str:
    """Normalize Unicode text to ASCII for JSON compatibility."""
    # Define common problematic Unicode characters and their replacements
    replacements = {
        '\u2026': '...',  # Ellipsis
        '\u2013': '-',    # En dash
        '\u2014': '--',   # Em dash
        '\u2018': "'",    # Left single quote
        '\u2019': "'",    # Right single quote
        '\u201C': '"',    # Left double quote
        '\u201D': '"',    # Right double quote
        '\u00A0': ' ',    # Non-breaking space
        '\u2022': '*',    # Bullet
        '\u2212': '-',    # Minus sign
    }
    
    # First apply direct replacements
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    # Then normalize and convert to ASCII
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(
        char if ord(char) < 128 else 
        unicodedata.normalize('NFKD', char).encode('ascii', 'ignore').decode('ascii') or ' '
        for char in normalized
    )


@retry(max_retries=3)  # Will use the config's value when called
def call_api(config: DelphiConfig, payload: JsonDict) -> JsonDict:
    """Make API call with retry logic."""
    url = f"{config.base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    logger.info("Making API call")
    response = requests.post(
        url, 
        json=payload, 
        headers=headers, 
        timeout=config.api_timeout
    )
    
    if response.status_code != 200:
        raise Exception(f"API Error {response.status_code}: {response.text}")
    
    return response.json()


def extract_json_blocks(text: str) -> List[str]:
    """Extract potential JSON blocks from text."""
    # Try to find JSON in code blocks
    code_blocks = re.findall(r'```(?:json)?(.*?)```', text, re.DOTALL)
    if code_blocks:
        return code_blocks
    
    # Then look for JSON-like objects starting with { and containing "responses"
    json_blocks = re.findall(r'(\{.*"responses".*\})', text, re.DOTALL)
    if json_blocks:
        return json_blocks
    
    # If we can't find a clearly defined JSON block, return the whole text
    return [text]


def validate_response(config: DelphiConfig, i: int, response: JsonDict) -> JsonDict:
    """Validate and normalize a single response."""
    # Start with a copy of the response to avoid modifying the original
    resp = response.copy()
    
    # Set correct question number
    resp["question"] = i + 1
    
    # Validate rating
    min_rating, max_rating = config.rating_range
    if "rating" not in resp or not isinstance(resp["rating"], (int, float)):
        resp["rating"] = Rating.NEUTRAL.value
        logger.warning(f"Missing or invalid rating for question {i+1}, setting to neutral (4)")
    else:
        orig_rating = resp["rating"]
        resp["rating"] = max(min_rating, min(max_rating, int(resp["rating"])))
        if resp["rating"] != orig_rating:
            logger.warning(f"Rating out of range ({orig_rating}) for question {i+1}, clamped to {resp['rating']}")
    
    # Validate confidence
    min_conf, max_conf = config.confidence_range
    if "confidence" not in resp or not isinstance(resp["confidence"], (int, float)):
        resp["confidence"] = Confidence.MODERATE.value
        logger.warning(f"Missing or invalid confidence for question {i+1}, setting to moderate (3)")
    else:
        orig_conf = resp["confidence"]
        resp["confidence"] = max(min_conf, min(max_conf, int(resp["confidence"])))
        if resp["confidence"] != orig_conf:
            logger.warning(f"Confidence out of range ({orig_conf}) for question {i+1}, clamped to {resp['confidence']}")
    
    # Validate and normalize text fields
    for field in ["position_summary", "detailed_explanation"]:
        if field not in resp:
            resp[field] = f"No {field.replace('_', ' ')} for question {i+1}"
            logger.warning(f"Missing {field} for question {i+1}")
        else:
            resp[field] = normalize_text(resp[field])
    
    return resp


def validate_and_cleanup_structure(config: DelphiConfig, parsed: JsonDict) -> JsonDict:
    """Validate and clean up the parsed JSON structure."""
    result = parsed.copy()
    
    # Ensure responses array exists
    if "responses" not in result:
        logger.warning("'responses' field missing, adding default structure")
        result["responses"] = []
    
    # Ensure we have the right number of responses - fill missing or trim extra
    while len(result["responses"]) < config.question_count:
        q_num = len(result["responses"]) + 1
        logger.warning(f"Missing response for question {q_num}, adding default")
        result["responses"].append({
            "question": q_num,
            "rating": Rating.NEUTRAL.value,  # Default neutral
            "position_summary": f"Missing response for question {q_num}",
            "detailed_explanation": f"No response provided for question {q_num}",
            "confidence": Confidence.MODERATE.value  # Default moderate confidence
        })
    
    if len(result["responses"]) > config.question_count:
        logger.warning(f"Too many responses ({len(result['responses'])}), trimming to {config.question_count}")
        result["responses"] = result["responses"][:config.question_count]
    
    # Validate and normalize each response
    validate = partial(validate_response, config)
    result["responses"] = [
        validate(i, resp) for i, resp in enumerate(result["responses"])
    ]
    
    return result


def try_parse_json(config: DelphiConfig, block: str, character: str, 
                  parser: Callable[[str], JsonDict], 
                  parser_name: str) -> Optional[JsonDict]:
    """Try to parse a block of text using the specified parser."""
    try:
        parsed = parser(block)
        if "responses" in parsed:
            logger.info(f"Successfully parsed JSON using {parser_name}")
            save_debug_file(
                config, 
                character, 
                json.dumps(parsed, indent=2), 
                f"parsed_{parser_name}"
            )
            return validate_and_cleanup_structure(config, parsed)
    except Exception as e:
        logger.warning(f"{parser_name} parsing failed: {str(e)}")
    return None


def extract_json(config: DelphiConfig, text: str, character: str) -> JsonDict:
    """Extract and parse JSON from text using multiple methods."""
    # Save the original response for debugging
    save_debug_file(config, character, text, "raw_response")
    
    try:
        # First normalize the text to handle special Unicode characters
        text = normalize_text(text)
        save_debug_file(config, character, text, "normalized_response")
        
        # Extract potential JSON blocks
        json_blocks = extract_json_blocks(text)
        
        # Define parsers with partial application
        parsers = [
            ("hjson", hjson.loads), 
            ("standard_json", json.loads)
        ]
        
        # Try each block with each parser until one succeeds
        for block in json_blocks:
            for parser_name, parser_func in parsers:
                result = try_parse_json(config, block, character, parser_func, parser_name)
                if result:
                    return result
        
        # If all parsing attempts fail, use a fallback structure
        logger.warning(f"Failed to parse JSON for {character}, using fallback structure")
        
        # Create a default response for each question
        default_responses = [
            {
                "question": i+1,
                "rating": Rating.NEUTRAL.value,
                "position_summary": f"Fallback summary for question {i+1}",
                "detailed_explanation": f"Unable to parse response for question {i+1}",
                "confidence": Confidence.MODERATE.value
            } 
            for i in range(config.question_count)
        ]
        
        fallback = {"responses": default_responses}
        
        save_debug_file(config, character, json.dumps(fallback, indent=2), "fallback_json")
        return fallback
        
    except Exception as e:
        logger.error(f"Error in extract_json for {character}: {str(e)}")
        
        # Return minimal valid structure as fallback
        logger.info(f"Using emergency fallback response structure for {character}")
        
        # Create error responses for each question
        error_responses = [
            {
                "question": i+1,
                "rating": Rating.NEUTRAL.value,
                "position_summary": f"Error parsing response for question {i+1}",
                "detailed_explanation": f"Error processing the response: {str(e)}",
                "confidence": Confidence.MODERATE.value
            } 
            for i in range(config.question_count)
        ]
        
        return {"responses": error_responses}


def format_markdown(character: str, data: JsonDict) -> str:
    """Convert JSON response to markdown format."""
    character_name = character.replace("-", " ").title()
    
    # Start with the title
    markdown_parts = [f"# {character_name}'s Response to the Dragon's Teeth Dilemma\n"]
    
    # Generate markdown for each response
    for response in data["responses"]:
        q_num = response["question"]
        
        # Get the question text (safely)
        if 1 <= q_num <= len(QUESTIONS):
            question = QUESTIONS[q_num-1]
        else:
            question = f"Question {q_num}"
        
        # Get rating and confidence descriptions
        rating = response.get("rating", Rating.NEUTRAL.value)
        rating_desc = RATING_DESCRIPTIONS.get(rating, RATING_DESCRIPTIONS[Rating.NEUTRAL.value])
        
        confidence = response.get("confidence", Confidence.MODERATE.value)
        # Ensure confidence is within bounds to prevent index error
        confidence_idx = min(max(confidence-1, 0), len(CONFIDENCE_DESCRIPTIONS)-1)
        confidence_desc = CONFIDENCE_DESCRIPTIONS[confidence_idx]
        
        # Format this response section
        section = [
            f"## Question {q_num}: {question}",
            f"**Rating:** {rating} {rating_desc}",
            f"**Position Summary:** {response.get('position_summary', 'No summary provided')}\n",
            f"**Detailed Explanation:** {response.get('detailed_explanation', 'No explanation provided')}\n",
            f"**Confidence:** {confidence} ({confidence_desc})\n"
        ]
        
        markdown_parts.extend(section)
    
    return "\n".join(markdown_parts)


def save_response(config: DelphiConfig, character: str, 
                 data: JsonDict, markdown: str) -> bool:
    """Save response as both JSON and Markdown using pathlib."""
    try:
        # Define file paths
        json_path = config.output_dir / f"{character}.json"
        md_path = config.output_dir / f"{character}.md"
        
        # Write files using pathlib methods
        json_path.write_text(
            json.dumps(data, indent=2), 
            encoding="utf-8"
        )
        
        md_path.write_text(
            markdown, 
            encoding="utf-8"
        )
        
        logger.info(f"Saved response for {character}")
        return True
    except Exception as e:
        logger.error(f"Error saving response for {character}: {str(e)}")
        return False


def generate_character_response(config: DelphiConfig, character: str) -> Optional[JsonDict]:
    """Generate response from a character."""
    # Load character profile
    profile_path = find_file(character, extensions=['.txt'])
    if not profile_path:
        logger.error(f"No profile found for {character}")
        return None
    
    profile = load_file(profile_path)
    if not profile:
        return None
    
    # Load questionnaire
    questionnaire_path = find_file('initial-question', extensions=['.md']) or \
                        find_file('questionnaire', extensions=['.md'])
    if not questionnaire_path:
        logger.error("Questionnaire not found")
        return None
    
    questionnaire = load_file(questionnaire_path)
    if not questionnaire:
        return None
    
    # Construct system message
    system_msg = (
        "You are participating in an ethical analysis of a difficult decision. "
        "The scenario involves whether to revive (wake up) an ancient group of warriors "
        "who have been in a special sleep for 900 years using advanced technology. "
        "These warriors were once powerful and potentially dangerous. Respond as specified in "
        "the character profile, considering the unique worldview, values, and decision-making style. "
        "Analyze the dilemma from this perspective without explicitly stating \"As [Character]\" "
        "or \"I am [Character].\" Your reasoning should authentically reflect the character's "
        "thought patterns and values.\n\n"
        "IMPORTANT: Your response MUST be properly formatted JSON with the following structure:\n"
        + EXAMPLE_JSON + "\n"
        "Your JSON must:\n"
        "1. Include 6 questions, numbered 1-6\n"
        "2. For each question, include a rating (1-7), position_summary, detailed_explanation, and confidence (1-5)\n"
        "3. Use only standard ASCII characters in your JSON (no fancy quotes or special characters)\n"
        "4. Not include any text before or after the JSON object\n\n"
        "Return only the JSON object and nothing else."
    )
    
    # Construct API request
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"{profile}\n\n{questionnaire}"}
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens
    }
    
    try:
        # Call API with retry logic built into the function
        call_with_config = partial(call_api, config)
        result = call_with_config(payload)
        content = result["choices"][0]["message"]["content"]
        
        # Log a sample of the response
        content_preview = content[:100] + "..." if len(content) > 100 else content
        logger.info(f"Received response for {character}, length: {len(content)} chars")
        logger.info(f"Preview: {content_preview}")
        
        # Parse and validate response
        return extract_json(config, content, character)
    
    except Exception as e:
        logger.error(f"Error generating response for {character}: {str(e)}")
        return None


def run_delphi_round_one(config: DelphiConfig) -> None:
    """Execute the first round of the Delphi Method."""
    logger.info(f"Starting Delphi Method - Round One")
    logger.info(f"Using API URL: {config.base_url}")
    
    all_responses = {}
    successful = []
    failed = []
    
    for character in config.characters:
        logger.info(f"Processing {character}")
        
        # Get response
        response_data = generate_character_response(config, character)
        if not response_data:
            logger.error(f"Failed to get valid response for {character}")
            failed.append(character)
            continue
        
        # Format as markdown
        markdown = format_markdown(character, response_data)
        
        # Save response
        if save_response(config, character, response_data, markdown):
            all_responses[character] = response_data
            successful.append(character)
            logger.info(f"Successfully processed {character}")
        else:
            failed.append(character)
        
        # Brief pause to avoid overwhelming the API
        time.sleep(2)
    
    # Save composite JSON if we have any successful responses
    if all_responses:
        try:
            composite_path = config.output_dir / config.composite_json
            composite_path.write_text(
                json.dumps(all_responses, indent=2),
                encoding="utf-8"
            )
            
            logger.info(f"Round One complete. Results saved to {composite_path}")
            
            # Clean up individual JSON files
            logger.info("Cleaning up individual JSON files...")
            for character in successful:
                json_path = config.output_dir / f"{character}.json"
                if json_path.exists():
                    json_path.unlink()  # Delete the file
                    logger.info(f"Removed {json_path}")
            
            if successful:
                logger.info(f"Successfully processed: {', '.join(successful)}")
            
            if failed:
                logger.warning(f"Failed to process: {', '.join(failed)}")
                
        except Exception as e:
            logger.error(f"Error saving composite JSON: {str(e)}")
    else:
        logger.error("No successful responses were generated")
    
    # Generate summary report
    logger.info("=== Delphi Round One Summary ===")
    logger.info(f"Total characters: {len(config.characters)}")
    logger.info(f"Successfully processed: {len(successful)} characters")
    logger.info(f"Failed: {len(failed)} characters")
    if failed:
        logger.info(f"Failed characters: {', '.join(failed)}")
    logger.info(f"Results saved to: {config.output_dir}")
    logger.info(f"Debug files saved to: {config.debug_dir}")


def main():
    """Main entry point for the script."""
    # Create the configuration
    config = DelphiConfig()
    
    # Set up logging
    global logger
    logger = setup_logging(config)
    
    logger.info(f"Delphi Method Simulation started")
    run_delphi_round_one(config)


if __name__ == "__main__":
    main()
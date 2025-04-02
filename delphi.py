#!/usr/bin/env python3
"""
Delphi Method Simulation - A simplified implementation for character-based ethical analysis.
"""
import requests
import json
import hjson
import time
import os
import re
import logging
import unicodedata
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union, Callable

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('delphi')

# Configuration
CONFIG = {
    # API settings
    'base_url': 'http://localhost:12434/engines/llama.cpp/v1',
    'model': 'ai/gemma3',
    'temperature': 0.7,
    'max_tokens': 2048,
    'api_timeout': 120,
    'api_max_retries': 3,
    
    # Output settings
    'output_dir': 'delphi_round1',
    'composite_json': 'round1_responses.json',
    'log_file': 'delphi_process.log',
    'debug_dir': 'debug_output',  # Directory for debugging output
    
    # Response parameters
    'question_count': 6,
    'rating_range': (1, 7),  # min, max
    'confidence_range': (1, 5),  # min, max
    
    # Character list
    'characters': [
        "bugs-bunny", "rick-sanchez", "stewie-griffin", "doraemon",
        "sandy-cheeks", "yoda", "bender", "stimpy", 
        "lisa-simpson", "twilight-sparkle"
    ]
}

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
    1: "(Strongly against waking them)",
    2: "(Against waking them)",
    3: "(Against waking them)",
    4: "(Neutral/Uncertain)",
    5: "(Favor waking them)",
    6: "(Favor waking them)",
    7: "(Strongly favor waking them)"
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

# Initialize output directory and debug directory
Path(CONFIG['output_dir']).mkdir(exist_ok=True)
Path(CONFIG['debug_dir']).mkdir(exist_ok=True)

# Set up file handler for logging
file_handler = logging.FileHandler(CONFIG['log_file'], mode='w')
file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
logger.addHandler(file_handler)


def retry(max_retries=3, backoff_factor=2):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        logger.error(f"All {max_retries} attempts failed. Last error: {str(e)}")
                        raise
                    wait_time = backoff_factor ** (attempt - 1)
                    logger.warning(f"Attempt {attempt} failed: {str(e)}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        return wrapper
    return decorator


def find_file(name: str, extensions: List[str] = None, locations: List[str] = None) -> Optional[str]:
    """Find a file by name, with optional extensions and locations."""
    extensions = extensions or ['']  # Default to no extension
    locations = locations or ['', 'profiles/']  # Current dir and profiles dir
    
    # If name has a hyphen, also try the base name
    base_names = [name]
    if '-' in name:
        base_names.append(name.split('-')[0])
    
    # Try each combination using a generator expression
    for base_name in base_names:
        for location in locations:
            for ext in extensions:
                path = Path(location) / f"{base_name}{ext}"
                if path.exists():
                    logger.info(f"Found file: {path}")
                    return str(path)
    
    return None


def load_file(path: str) -> Optional[str]:
    """Load file content from path."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error loading file {path}: {str(e)}")
        return None


def save_debug_file(character: str, content: str, suffix: str = "raw"):
    """Save content to a debug file for inspection."""
    try:
        debug_path = Path(CONFIG['debug_dir']) / f"{character}_{suffix}.txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved debug file: {debug_path}")
    except Exception as e:
        logger.error(f"Error saving debug file for {character}: {str(e)}")


def normalize_text(text: str) -> str:
    """Normalize Unicode text to ASCII for JSON compatibility."""
    # First, normalize Unicode using NFKD form (compatibility decomposition)
    normalized = unicodedata.normalize('NFKD', text)
    
    # Replace specific problematic Unicode characters
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
    
    # Apply all replacements at once
    for char, replacement in replacements.items():
        normalized = normalized.replace(char, replacement)
    
    # Convert non-ASCII characters to ASCII equivalents or spaces
    return ''.join(
        char if ord(char) < 128 else 
        unicodedata.normalize('NFKD', char).encode('ascii', 'ignore').decode('ascii') or ' '
        for char in normalized
    )


@retry(max_retries=CONFIG['api_max_retries'])
def call_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Make API call with retry logic."""
    url = f"{CONFIG['base_url']}/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    logger.info("Making API call")
    response = requests.post(url, json=payload, headers=headers, timeout=CONFIG['api_timeout'])
    
    if response.status_code != 200:
        raise Exception(f"API Error {response.status_code}: {response.text}")
    
    return response.json()


def extract_json_blocks(text: str) -> List[str]:
    """Extract potential JSON blocks from text."""
    # Use list comprehension to collect all potential JSON blocks
    return (
        # First try to find JSON in code blocks
        re.findall(r'```(?:json)?(.*?)```', text, re.DOTALL) or
        # Then look for JSON-like objects starting with { and containing "responses"
        re.findall(r'(\{.*"responses".*\})', text, re.DOTALL) or
        # If we can't find a clearly defined JSON block, return the whole text
        [text]
    )


def validate_response(i: int, response: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a single response."""
    # Start with a copy of the response to avoid modifying the original
    resp = response.copy()
    
    # Set correct question number
    resp["question"] = i + 1
    
    # Validate rating
    min_rating, max_rating = CONFIG['rating_range']
    if "rating" not in resp or not isinstance(resp["rating"], (int, float)):
        resp["rating"] = 4
        logger.warning(f"Missing or invalid rating for question {i+1}, setting to neutral (4)")
    else:
        orig_rating = resp["rating"]
        resp["rating"] = max(min_rating, min(max_rating, int(resp["rating"])))
        if resp["rating"] != orig_rating:
            logger.warning(f"Rating out of range ({orig_rating}) for question {i+1}, clamped to {resp['rating']}")
    
    # Validate confidence
    min_conf, max_conf = CONFIG['confidence_range']
    if "confidence" not in resp or not isinstance(resp["confidence"], (int, float)):
        resp["confidence"] = 3
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


def validate_and_cleanup_structure(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean up the parsed JSON structure."""
    result = parsed.copy()
    
    # Ensure responses array exists
    if "responses" not in result:
        logger.warning("'responses' field missing, adding default structure")
        result["responses"] = []
    
    # Ensure we have the right number of responses - fill missing or trim extra
    while len(result["responses"]) < CONFIG['question_count']:
        q_num = len(result["responses"]) + 1
        logger.warning(f"Missing response for question {q_num}, adding default")
        result["responses"].append({
            "question": q_num,
            "rating": 4,  # Default neutral
            "position_summary": f"Missing response for question {q_num}",
            "detailed_explanation": f"No response provided for question {q_num}",
            "confidence": 3  # Default moderate confidence
        })
    
    if len(result["responses"]) > CONFIG['question_count']:
        logger.warning(f"Too many responses ({len(result['responses'])}), trimming to {CONFIG['question_count']}")
        result["responses"] = result["responses"][:CONFIG['question_count']]
    
    # Validate and normalize each response
    result["responses"] = [
        validate_response(i, resp) for i, resp in enumerate(result["responses"])
    ]
    
    return result


def try_parse(block: str, character: str, parser: Callable, parser_name: str) -> Optional[Dict[str, Any]]:
    """Try to parse a block of text using the specified parser."""
    try:
        parsed = parser(block)
        if "responses" in parsed:
            logger.info(f"Successfully parsed JSON using {parser_name}")
            save_debug_file(character, json.dumps(parsed, indent=2), f"parsed_{parser_name}")
            return validate_and_cleanup_structure(parsed)
    except Exception as e:
        logger.warning(f"{parser_name} parsing failed: {str(e)}")
    return None


def extract_json(text: str, character: str) -> Dict[str, Any]:
    """Extract and parse JSON from text using hjson for better compatibility."""
    try:
        # Save the original response for debugging
        save_debug_file(character, text, "raw_response")
        
        # First normalize the text to handle special Unicode characters
        text = normalize_text(text)
        save_debug_file(character, text, "normalized_response")
        
        # Extract potential JSON blocks
        json_blocks = extract_json_blocks(text)
        
        # Try parsing with each parser in priority order
        parsers = [("hjson", hjson.loads), ("standard_json", json.loads)]
        
        # Try each block with each parser until one succeeds
        for block in json_blocks:
            for parser_name, parser_func in parsers:
                result = try_parse(block, character, parser_func, parser_name)
                if result:
                    return result
        
        # If all parsing attempts fail, use a fallback structure
        logger.warning(f"Failed to parse JSON for {character}, using fallback structure")
        fallback = {
            "responses": [
                {
                    "question": i+1,
                    "rating": 4,
                    "position_summary": f"Fallback summary for question {i+1}",
                    "detailed_explanation": f"Unable to parse response for question {i+1}",
                    "confidence": 3
                } for i in range(CONFIG['question_count'])
            ]
        }
        
        save_debug_file(character, json.dumps(fallback, indent=2), "fallback_json")
        return fallback
        
    except Exception as e:
        logger.error(f"Error in extract_json for {character}: {str(e)}")
        
        # Return minimal valid structure as fallback
        logger.info(f"Using fallback response structure for {character}")
        return {
            "responses": [
                {
                    "question": i+1,
                    "rating": 4,
                    "position_summary": f"Error parsing response for question {i+1}",
                    "detailed_explanation": f"Error processing the response: {str(e)}",
                    "confidence": 3
                } for i in range(CONFIG['question_count'])
            ]
        }


def format_markdown(character: str, data: Dict[str, Any]) -> str:
    """Convert JSON response to markdown format."""
    character_name = character.replace("-", " ").title()
    markdown = [f"# {character_name}'s Response to the Dragon's Teeth Dilemma\n"]
    
    # Use list comprehension for generating markdown sections
    sections = []
    for response in data["responses"]:
        q_num = response["question"]
        question = QUESTIONS[q_num-1] if 1 <= q_num <= len(QUESTIONS) else f"Question {q_num}"
        rating = response.get("rating", 4)
        
        # Get rating description using the lookup table
        rating_desc = RATING_DESCRIPTIONS.get(rating, RATING_DESCRIPTIONS[4])
        
        # Get confidence description using the lookup table
        confidence = response.get("confidence", 3)
        confidence_desc = CONFIDENCE_DESCRIPTIONS[min(confidence-1, 4)]
        
        # Create section for this response
        section = [
            f"## Question {q_num}: {question}",
            f"**Rating:** {rating} {rating_desc}",
            f"**Position Summary:** {response.get('position_summary', 'No summary provided')}\n",
            f"**Detailed Explanation:** {response.get('detailed_explanation', 'No explanation provided')}\n",
            f"**Confidence:** {confidence} ({confidence_desc})\n"
        ]
        sections.extend(section)
    
    markdown.extend(sections)
    return "\n".join(markdown)


def save_response(character: str, data: Dict[str, Any], markdown: str) -> bool:
    """Save response as both JSON and Markdown. Returns success status."""
    try:
        output_dir = Path(CONFIG['output_dir'])
        
        # Save JSON
        with open(output_dir / f"{character}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Save Markdown
        with open(output_dir / f"{character}.md", "w", encoding="utf-8") as f:
            f.write(markdown)
        
        logger.info(f"Saved response for {character}")
        return True
    except Exception as e:
        logger.error(f"Error saving response for {character}: {str(e)}")
        return False


def generate_character_response(character: str) -> Optional[Dict[str, Any]]:
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
    questionnaire_path = find_file('initial-question', extensions=['.md']) or find_file('questionnaire', extensions=['.md'])
    if not questionnaire_path:
        logger.error("Questionnaire not found")
        return None
    
    questionnaire = load_file(questionnaire_path)
    if not questionnaire:
        return None
    
    # Construct API request with improved system message
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
    
    payload = {
        "model": CONFIG['model'],
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"{profile}\n\n{questionnaire}"}
        ],
        "temperature": CONFIG['temperature'],
        "max_tokens": CONFIG['max_tokens']
    }
    
    try:
        # Call API
        result = call_api(payload)
        content = result["choices"][0]["message"]["content"]
        
        # Log a sample of the response
        logger.info(f"Received response for {character}, length: {len(content)} chars")
        
        # Parse and validate response
        return extract_json(content, character)
    
    except Exception as e:
        logger.error(f"Error generating response for {character}: {str(e)}")
        return None


def run_delphi_round_one() -> None:
    """Execute the first round of the Delphi Method."""
    logger.info("Starting Delphi Method - Round One")
    
    all_responses = {}
    successful = []
    failed = []
    
    for character in CONFIG['characters']:
        logger.info(f"Processing {character}")
        
        # Get response
        response_data = generate_character_response(character)
        if not response_data:
            logger.error(f"Failed to get valid response for {character}")
            failed.append(character)
            continue
        
        # Format as markdown
        markdown = format_markdown(character, response_data)
        
        # Save response
        if save_response(character, response_data, markdown):
            all_responses[character] = response_data
            successful.append(character)
            logger.info(f"Successfully processed {character}")
        else:
            failed.append(character)
        
        # Brief pause to avoid overwhelming the API
        time.sleep(2)
    
    # Save composite JSON
    if all_responses:
        try:
            with open(Path(CONFIG['output_dir']) / CONFIG['composite_json'], "w", encoding="utf-8") as f:
                json.dump(all_responses, f, indent=2)
            
            logger.info(f"Round One complete. Results saved to {CONFIG['output_dir']}/{CONFIG['composite_json']}")
            logger.info(f"Successfully processed: {', '.join(successful)}")
            
            if failed:
                logger.warning(f"Failed to process: {', '.join(failed)}")
        except Exception as e:
            logger.error(f"Error saving composite JSON: {str(e)}")
    else:
        logger.error("No successful responses were generated")
        
    # Summary report
    logger.info("=== Delphi Round One Summary ===")
    logger.info(f"Total characters: {len(CONFIG['characters'])}")
    logger.info(f"Successfully processed: {len(successful)} characters")
    logger.info(f"Failed: {len(failed)} characters")
    if failed:
        logger.info(f"Failed characters: {', '.join(failed)}")
    logger.info(f"Debug files saved to {CONFIG['debug_dir']}")


if __name__ == "__main__":
    logger.info(f"Delphi Method Simulation started")
    run_delphi_round_one()
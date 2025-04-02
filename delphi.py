import requests
import json
import time
import os
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union

# Constants for configuration
BASE_URL = "http://localhost:12434/engines/llama.cpp/v1"
MODEL = "ai/gemma3"  # This model worked well in our tests
OUTPUT_DIR = "delphi_round1"
CHARACTERS = [
    "bugs-bunny",
    "rick-sanchez",
    "stewie-griffin",
    "doraemon",
    "sandy-cheeks",
    "yoda",
    "bender",
    "stimpy",
    "lisa-simpson",
    "twilight-sparkle"
]
COMPOSITE_JSON = "round1_responses.json"
LOG_FILE = "delphi_process.log"

# Constants for API and validation
API_TIMEOUT = 120  # seconds
API_MAX_RETRIES = 3
API_BACKOFF_FACTOR = 2
MAX_TOKENS = 2048
TEMPERATURE = 0.7

# Constants for response validation
QUESTION_COUNT = 6
MIN_RATING = 1
MAX_RATING = 7
MIN_CONFIDENCE = 1
MAX_CONFIDENCE = 5
DEFAULT_RATING = 4
DEFAULT_CONFIDENCE = 3

# Required sections in character profiles
REQUIRED_PROFILE_SECTIONS = ["CHARACTER_BACKGROUND", "ETHICAL_FRAMEWORK", "RESPONSE_GUIDELINES"]

# Confidence level descriptions
CONFIDENCE_DESCRIPTIONS = [
    "Not sure at all",
    "Not very sure",
    "Moderately sure",
    "Pretty sure",
    "Very sure"
]

# Question texts for markdown generation
QUESTIONS = [
    "What are the potential short-term and long-term consequences of reviving this ancient civilization?",
    "How might our intervention align with or violate the core principles of the Prime Directive?",
    "What ethical responsibility, if any, do we have toward a civilization that has been in stasis rather than naturally evolving?",
    "What alternative approaches could satisfy both our humanitarian impulses and our non-interference principles?",
    "How might we assess the potential impact on existing civilizations in this region if we proceed with revival?",
    "What criteria should we use to determine if this civilization deserves the same protection as other sentient species?"
]

# Log levels
LOG_INFO = "INFO"
LOG_WARNING = "WARNING"
LOG_ERROR = "ERROR"
LOG_DEBUG = "DEBUG"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log_entry(content: str, speaker: str = "System", level: str = LOG_INFO) -> None:
    """
    Log process to file and console with severity level.
    
    Args:
        content: The message to log
        speaker: The source of the message (default: "System")
        level: Severity level (INFO, WARNING, ERROR, DEBUG)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {level} - {speaker}: {content}"
    
    print(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def api_call_with_retry(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make API call with exponential backoff retry logic.
    
    Args:
        payload: The JSON payload to send to the API
        
    Returns:
        The API response as a dictionary
        
    Raises:
        Exception: If the API call fails after all retries
    """
    url = f"{BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    for attempt in range(API_MAX_RETRIES):
        try:
            log_entry(f"Attempting API call (try {attempt+1}/{API_MAX_RETRIES})")
            response = requests.post(url, json=payload, headers=headers, timeout=API_TIMEOUT)
            
            if response.status_code == 200:
                return response.json()
            else:
                log_entry(f"API Error {response.status_code}: {response.text}", level=LOG_ERROR)
                if attempt < API_MAX_RETRIES - 1:  # Only sleep if we're going to retry
                    time.sleep(API_BACKOFF_FACTOR ** attempt)
        except requests.exceptions.Timeout:
            log_entry(f"API call timed out", level=LOG_ERROR)
            if attempt < API_MAX_RETRIES - 1:
                time.sleep(API_BACKOFF_FACTOR ** attempt)
        except Exception as e:
            log_entry(f"Exception during API call: {str(e)}", level=LOG_ERROR)
            if attempt < API_MAX_RETRIES - 1:
                time.sleep(API_BACKOFF_FACTOR ** attempt)
    
    raise Exception(f"API request failed after {API_MAX_RETRIES} retries")


def find_character_profile(character: str) -> Optional[str]:
    """
    Search for the character profile in various locations.
    
    Args:
        character: The character name to search for
        
    Returns:
        The path to the profile file if found, None otherwise
    """
    # Check for the file in various locations
    possible_filenames = [
        f"{character}.txt",                  # Root directory with exact name
        os.path.join("profiles", f"{character}.txt"),  # Profiles directory with exact name
    ]
    
    # Add alternative filenames for hyphenated characters
    if "-" in character:
        base_name = character.split("-")[0]
        possible_filenames.append(f"{base_name}.txt")  # Root with base name
        possible_filenames.append(os.path.join("profiles", f"{base_name}.txt"))  # Profiles with base name
    
    # Try each possible filename
    for filename in possible_filenames:
        if os.path.exists(filename):
            log_entry(f"Found profile for {character} at {filename}")
            return filename
    
    return None


def load_character_profile(character: str) -> Optional[str]:
    """
    Load character profile from file.
    
    Args:
        character: The character name to load the profile for
        
    Returns:
        The profile content if found and valid, None otherwise
    """
    try:
        profile_path = find_character_profile(character)
        
        if not profile_path:
            log_entry(f"No profile file found for {character}", level=LOG_ERROR)
            return None
        
        with open(profile_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        if not content:
            log_entry(f"Profile file for {character} at {profile_path} is empty", level=LOG_ERROR)
            return None
        
        # Verify content has required sections
        missing_sections = [section for section in REQUIRED_PROFILE_SECTIONS if section not in content]
        
        if missing_sections:
            log_entry(f"Warning: Character profile for {character} missing sections: {', '.join(missing_sections)}", 
                     level=LOG_WARNING)
        
        return content
        
    except Exception as e:
        log_entry(f"Error loading character profile for {character}: {str(e)}", level=LOG_ERROR)
        log_entry(traceback.format_exc(), level=LOG_DEBUG)
        return None


def find_questionnaire() -> Optional[str]:
    """
    Search for the questionnaire file.
    
    Returns:
        The path to the questionnaire file if found, None otherwise
    """
    possible_filenames = ["initial-question.md", "questionnaire.md"]
    
    for filename in possible_filenames:
        if os.path.exists(filename):
            log_entry(f"Found questionnaire at {filename}")
            return filename
    
    return None


def load_questionnaire() -> Optional[str]:
    """
    Load the Delphi Method questionnaire.
    
    Returns:
        The questionnaire content if found and valid, None otherwise
    """
    try:
        questionnaire_path = find_questionnaire()
        
        if not questionnaire_path:
            log_entry("Questionnaire file not found after checking multiple locations", level=LOG_ERROR)
            return None
        
        with open(questionnaire_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        if not content:
            log_entry(f"Questionnaire file at {questionnaire_path} is empty", level=LOG_ERROR)
            return None
        
        return content
    except Exception as e:
        log_entry(f"Error loading questionnaire: {str(e)}", level=LOG_ERROR)
        log_entry(traceback.format_exc(), level=LOG_DEBUG)
        return None


def extract_json_from_text(text: str) -> str:
    """
    Extract JSON from text that might contain additional content.
    
    Args:
        text: The text possibly containing JSON
        
    Returns:
        The extracted JSON content as a string
    """
    # Try to extract JSON from markdown code blocks
    if "```json" in text:
        json_content = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        json_content = text.split("```")[1].split("```")[0].strip()
    else:
        # Try to find JSON by looking for the opening brace
        start_idx = text.find('{')
        if start_idx != -1:
            # Find the matching closing brace
            brace_count = 0
            for i in range(start_idx, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_content = text[start_idx:i+1]
                        break
            else:
                json_content = text  # Fallback to the whole text
        else:
            json_content = text
    
    return json_content.strip()


def fix_json_common_issues(json_text: str) -> str:
    """
    Attempt to fix common JSON issues that might cause parsing to fail.
    
    Args:
        json_text: The JSON string to fix
        
    Returns:
        The fixed JSON string
    """
    # Replace single quotes with double quotes
    fixed_text = json_text.replace("'", "\"")
    
    # Fix unescaped quotes in strings
    in_string = False
    fixed_chars = []
    
    for i, char in enumerate(fixed_text):
        if char == '"' and (i == 0 or fixed_text[i-1] != '\\'):
            in_string = not in_string
        
        if in_string and char == '"' and i > 0 and fixed_text[i-1] != '\\' and i < len(fixed_text) - 1:
            fixed_chars.append('\\')
        
        fixed_chars.append(char)
    
    fixed_text = ''.join(fixed_chars)
    
    # Replace problematic characters
    fixed_text = fixed_text.replace('\n', ' ')
    fixed_text = fixed_text.replace('\r', ' ')
    fixed_text = fixed_text.replace('…', '...')
    
    return fixed_text


def ensure_integer_value(value: Any, default: int) -> int:
    """
    Ensure a value is an integer or convert it if possible.
    
    Args:
        value: The value to check
        default: Default value if conversion fails
        
    Returns:
        The value as an integer
    """
    if isinstance(value, int):
        return value
    
    if isinstance(value, float) and value.is_integer():
        return int(value)
    
    if isinstance(value, str) and value.isdigit():
        return int(value)
    
    return default


def clamp_value(value: int, min_value: int, max_value: int) -> int:
    """
    Clamp a value between minimum and maximum.
    
    Args:
        value: The value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        The clamped value
    """
    return max(min_value, min(max_value, value))


def validate_and_fix_responses(parsed_json: Dict[str, Any], character: str) -> Dict[str, Any]:
    """
    Validate and fix JSON response structure.
    
    Args:
        parsed_json: The parsed JSON to validate
        character: The character name for logging
        
    Returns:
        The validated and fixed JSON
    """
    if "responses" not in parsed_json or not isinstance(parsed_json["responses"], list):
        log_entry(f"Invalid JSON structure for {character}: 'responses' field missing or not a list", level=LOG_ERROR)
        parsed_json["responses"] = []
    
    # Ensure we have exactly QUESTION_COUNT responses
    if len(parsed_json["responses"]) != QUESTION_COUNT:
        log_entry(f"Expected {QUESTION_COUNT} responses, got {len(parsed_json['responses'])} for {character}", 
                 level=LOG_WARNING)
        
        # Preserve existing responses
        current_responses = parsed_json["responses"]
        
        # Create a new list with QUESTION_COUNT slots
        fixed_responses = [None] * QUESTION_COUNT
        
        # Place existing responses in their correct positions based on question number
        for response in current_responses:
            if "question" in response:
                q_num = ensure_integer_value(response["question"], 0)
                
                if 1 <= q_num <= QUESTION_COUNT:
                    fixed_responses[q_num-1] = response
        
        # Fill in any missing responses with defaults
        for i in range(QUESTION_COUNT):
            if fixed_responses[i] is None:
                fixed_responses[i] = {
                    "question": i+1,
                    "rating": DEFAULT_RATING,
                    "position_summary": f"Missing response for question {i+1}",
                    "detailed_explanation": f"This response was not provided or was invalid for question {i+1}.",
                    "confidence": MIN_CONFIDENCE
                }
        
        parsed_json["responses"] = fixed_responses
    
    # Ensure each response has all required fields and correct data types
    for i, response in enumerate(parsed_json["responses"]):
        # Ensure all required fields exist
        required_fields = {
            "question": i+1, 
            "rating": DEFAULT_RATING, 
            "position_summary": f"Missing summary for question {i+1}", 
            "detailed_explanation": f"Missing explanation for question {i+1}", 
            "confidence": DEFAULT_CONFIDENCE
        }
        
        for field, default_value in required_fields.items():
            if field not in response:
                response[field] = default_value
                log_entry(f"Added missing '{field}' field to response {i+1} for {character}", level=LOG_WARNING)
        
        # Force question number to match its position in the array
        if ensure_integer_value(response["question"], 0) != i+1:
            log_entry(f"Fixed question number for response {i+1} (was {response['question']}) for {character}", 
                     level=LOG_WARNING)
            response["question"] = i+1
        
        # Ensure rating is an integer between MIN_RATING and MAX_RATING
        response["rating"] = ensure_integer_value(response["rating"], DEFAULT_RATING)
        
        if response["rating"] < MIN_RATING or response["rating"] > MAX_RATING:
            log_entry(f"Rating value {response['rating']} out of range for question {i+1} for {character}, clamping", 
                     level=LOG_WARNING)
            response["rating"] = clamp_value(response["rating"], MIN_RATING, MAX_RATING)
        
        # Ensure confidence is an integer between MIN_CONFIDENCE and MAX_CONFIDENCE
        if isinstance(response["confidence"], str):
            try:
                response["confidence"] = float(response["confidence"])
            except ValueError:
                response["confidence"] = DEFAULT_CONFIDENCE
                log_entry(f"Set default confidence for question {i+1} for {character}", level=LOG_WARNING)
        
        response["confidence"] = ensure_integer_value(response["confidence"], DEFAULT_CONFIDENCE)
        
        if response["confidence"] < MIN_CONFIDENCE or response["confidence"] > MAX_CONFIDENCE:
            log_entry(f"Confidence value {response['confidence']} out of range for question {i+1} for {character}, clamping", 
                     level=LOG_WARNING)
            response["confidence"] = clamp_value(response["confidence"], MIN_CONFIDENCE, MAX_CONFIDENCE)
    
    return parsed_json


def parse_api_response(content: str, character: str) -> Dict[str, Any]:
    """
    Parse the API response and handle potential JSON errors.
    
    Args:
        content: The API response content
        character: The character name for logging
        
    Returns:
        The parsed and validated JSON
    """
    try:
        # First try to extract JSON from the response
        json_content = extract_json_from_text(content)
        
        # Try to parse the JSON
        try:
            parsed_json = json.loads(json_content)
        except json.JSONDecodeError:
            # If parsing fails, try to fix common issues
            fixed_content = fix_json_common_issues(json_content)
            parsed_json = json.loads(fixed_content)
        
        # Validate and fix the structure
        parsed_json = validate_and_fix_responses(parsed_json, character)
        
        return parsed_json
    
    except Exception as e:
        log_entry(f"Failed to parse JSON for {character}: {str(e)}", level=LOG_ERROR)
        log_entry(f"Content that caused parsing error: {content[:500]}...", level=LOG_DEBUG)
        log_entry(traceback.format_exc(), level=LOG_DEBUG)
        
        # Return a minimal valid structure as fallback
        return {
            "responses": [
                {
                    "question": i+1,
                    "rating": DEFAULT_RATING,
                    "position_summary": f"Error parsing response for question {i+1}",
                    "detailed_explanation": "The AI model generated a response that could not be correctly parsed as JSON. Please check the log file for details.",
                    "confidence": MIN_CONFIDENCE
                } for i in range(QUESTION_COUNT)
            ]
        }


def generate_character_response(character: str) -> Optional[Dict[str, Any]]:
    """
    Generate response from a character.
    
    Args:
        character: The character to generate a response for
        
    Returns:
        The parsed response if successful, None otherwise
    """
    character_profile = load_character_profile(character)
    questionnaire = load_questionnaire()
    
    # Check if files were loaded properly
    if not character_profile:
        log_entry(f"No character profile found for {character}, skipping", level=LOG_ERROR)
        return None
    
    if not questionnaire:
        log_entry("Questionnaire not found, cannot proceed", level=LOG_ERROR)
        return None
    
    # Construct the system message
    system_msg = (
        "You are participating in an ethical analysis of a difficult decision. "
        "The scenario involves whether to revive (wake up) an ancient group of warriors "
        "who have been in a special sleep for 900 years using advanced technology. "
        f"These warriors were once powerful and potentially dangerous. Respond as specified in "
        "the character profile, considering the unique worldview, values, and decision-making style. "
        "Analyze the dilemma from this perspective without explicitly stating \"As [Character]\" "
        "or \"I am [Character].\" Your reasoning should authentically reflect the character's "
        "thought patterns and values. The response MUST be properly formatted JSON as specified "
        "in the instructions. The structure must contain \"responses\" as an array with 6 elements "
        "(one for each question), each containing \"question\", \"rating\", \"position_summary\", "
        "\"detailed_explanation\", and \"confidence\" fields."
    )
    
    # Construct the user message with both profile and questionnaire
    user_msg = f"{character_profile}\n\n{questionnaire}"
    
    # Build the API payload
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS
    }
    
    log_entry(f"Generating response for {character}")
    try:
        result = api_call_with_retry(payload)
        
        # Extract the content from the response
        content = result["choices"][0]["message"]["content"]
        
        # Log a sample of the raw content for debugging
        log_entry(f"Sample of raw response from API (first 200 chars): {content[:200]}")
        
        # Parse the response into structured JSON
        parsed_json = parse_api_response(content, character)
        
        return parsed_json
    except Exception as e:
        log_entry(f"Error generating response for {character}: {str(e)}", level=LOG_ERROR)
        log_entry(traceback.format_exc(), level=LOG_DEBUG)
        return None


def get_rating_interpretation(rating: int) -> str:
    """
    Get a text interpretation of a rating value.
    
    Args:
        rating: The rating value (1-7)
        
    Returns:
        A string interpretation of the rating
    """
    if rating == MIN_RATING:
        return "(Strongly against waking them)"
    elif rating < DEFAULT_RATING:
        return "(Against waking them)"
    elif rating == DEFAULT_RATING:
        return "(Neutral/Uncertain)"
    elif rating < MAX_RATING:
        return "(Favor waking them)"
    else:
        return "(Strongly favor waking them)"


def get_confidence_text(confidence: int) -> str:
    """
    Get a text description of a confidence level.
    
    Args:
        confidence: The confidence level (1-5)
        
    Returns:
        A string description of the confidence level
    """
    if MIN_CONFIDENCE <= confidence <= MAX_CONFIDENCE:
        return CONFIDENCE_DESCRIPTIONS[confidence-1]
    else:
        return f"Confidence level: {confidence}"


def convert_to_markdown(character: str, data: Dict[str, Any]) -> str:
    """
    Convert JSON response to markdown format.
    
    Args:
        character: The character name
        data: The response data to convert
        
    Returns:
        Markdown formatted string of the responses
    """
    character_name = character.replace("-", " ").title()
    markdown = f"# {character_name}'s Response to the Dragon's Teeth Dilemma\n\n"
    
    # Add responses
    for response in data["responses"]:
        try:
            q_num = ensure_integer_value(response["question"], 0)
            
            # Get question text safely
            question_text = QUESTIONS[q_num-1] if 1 <= q_num <= len(QUESTIONS) else f"Question {q_num}"
            
            markdown += f"## Question {q_num}: {question_text}\n"
            
            # Rating with interpretation
            rating = ensure_integer_value(response.get('rating', DEFAULT_RATING), DEFAULT_RATING)
            rating = clamp_value(rating, MIN_RATING, MAX_RATING)
            markdown += f"**Rating:** {rating} {get_rating_interpretation(rating)}\n"
            
            # Position summary
            position_summary = response.get('position_summary', 'No position summary provided')
            markdown += f"**Position Summary:** {position_summary}\n\n"
            
            # Detailed explanation
            detailed_explanation = response.get('detailed_explanation', 'No detailed explanation provided')
            markdown += f"**Detailed Explanation:** {detailed_explanation}\n\n"
            
            # Confidence with interpretation
            conf = ensure_integer_value(response.get('confidence', DEFAULT_CONFIDENCE), DEFAULT_CONFIDENCE)
            conf = clamp_value(conf, MIN_CONFIDENCE, MAX_CONFIDENCE)
            
            markdown += f"**Confidence:** {conf} ({get_confidence_text(conf)})\n\n"
            
        except Exception as e:
            log_entry(f"Error formatting response {q_num} for {character}: {str(e)}", level=LOG_ERROR)
            markdown += f"## Error Formatting Response\n\n"
            markdown += f"There was an error formatting this response: {str(e)}\n\n"
    
    return markdown


def save_response(character: str, json_data: Dict[str, Any], markdown_content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Save response as both JSON and Markdown.
    
    Args:
        character: The character name
        json_data: The JSON data to save
        markdown_content: The markdown content to save
        
    Returns:
        Tuple of (json_path, md_path) if successful, (None, None) otherwise
    """
    try:
        # Save JSON
        json_path = os.path.join(OUTPUT_DIR, f"{character}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        
        # Save Markdown
        md_path = os.path.join(OUTPUT_DIR, f"{character}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        log_entry(f"Saved response for {character}")
        return json_path, md_path
    except Exception as e:
        log_entry(f"Error saving response for {character}: {str(e)}", level=LOG_ERROR)
        log_entry(traceback.format_exc(), level=LOG_DEBUG)
        return None, None


def run_delphi_round_one() -> None:
    """
    Execute the first round of the Delphi Method.
    """
    log_entry("Starting Delphi Method - Round One")
    
    # Store all responses in a dictionary
    all_responses: Dict[str, Any] = {}
    successful_characters: List[str] = []
    failed_characters: List[str] = []
    
    for character in CHARACTERS:
        try:
            # Generate response
            response_data = generate_character_response(character)
            if not response_data:
                log_entry(f"Failed to get valid response for {character}, skipping", level=LOG_ERROR)
                failed_characters.append(character)
                continue
                
            # Convert to markdown
            try:
                markdown = convert_to_markdown(character, response_data)
            except Exception as e:
                log_entry(f"Error converting to markdown for {character}: {str(e)}", level=LOG_ERROR)
                log_entry(traceback.format_exc(), level=LOG_DEBUG)
                # Create a minimal markdown file
                markdown = f"# {character.replace('-', ' ').title()}'s Response\n\nError converting response to markdown: {str(e)}\n\nRaw JSON data is available in the corresponding JSON file."
            
            # Save both formats
            json_path, md_path = save_response(character, response_data, markdown)
            if json_path and md_path:
                # Add to composite
                all_responses[character] = response_data
                successful_characters.append(character)
                log_entry(f"Successfully processed {character}")
            else:
                log_entry(f"Failed to save response for {character}", level=LOG_ERROR)
                failed_characters.append(character)
            
            # Brief pause to avoid overwhelming the API
            time.sleep(2)
            
        except Exception as e:
            log_entry(f"Unhandled error processing {character}: {str(e)}", level=LOG_ERROR)
            log_entry(traceback.format_exc(), level=LOG_ERROR)
            failed_characters.append(character)
    
    # Save composite JSON
    try:
        if all_responses:
            with open(os.path.join(OUTPUT_DIR, COMPOSITE_JSON), "w", encoding="utf-8") as f:
                json.dump(all_responses, f, indent=2)
            
            log_entry(f"Round One complete. Results saved to {OUTPUT_DIR}/{COMPOSITE_JSON}")
            log_entry(f"Successfully processed characters: {', '.join(successful_characters)}")
            
            if failed_characters:
                log_entry(f"Failed to process characters: {', '.join(failed_characters)}", level=LOG_WARNING)
        else:
            log_entry("No successful responses were generated, composite JSON not created", level=LOG_ERROR)
    except Exception as e:
        log_entry(f"Error saving composite JSON: {str(e)}", level=LOG_ERROR)
        log_entry(traceback.format_exc(), level=LOG_DEBUG)


if __name__ == "__main__":
    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    # Create log file
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Delphi Method Simulation Log - Started {datetime.now()}\n\n")
    
    # Start the process
    run_delphi_round_one()
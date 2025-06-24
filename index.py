import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template
import requests

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Monday.com API configuration
MONDAY_API_TOKEN = os.environ.get("MONDAY_API_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJ0aWQiOjQxMDM1MDMyNiwiYWFpIjoxMSwidWlkIjo1NTIyMDQ0LCJpYWQiOiIyMDI0LTA5LTEzVDExOjUyOjQzLjAwMFoiLCJwZXIiOiJtZTp3cml0ZSIsImFjdGlkIjozNzk1MywicmduIjoidXNlMSJ9.hwTlwMwtbhKdZsYcGT7UoENBLZUAxnfUXchj5RZJBz4")
MONDAY_API_URL = "https://api.monday.com/v2"

# In-memory storage for operation state (in production, use a database)
operation_state = {}

def make_monday_api_request(query, variables=None):
    """
    Make a request to Monday.com API
    In development, this returns mock data with detailed comments
    """
    headers = {
        "Authorization": f"Bearer {MONDAY_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query,
        "variables": variables or {}
    }
    
    logger.debug(f"Monday API Request: {json.dumps(payload, indent=2)}")
    
    # Real API call
    response = None
    try:
        response = requests.post(MONDAY_API_URL, json=payload, headers=headers)
        logger.debug(f"API Response Status: {response.status_code}")
        logger.debug(f"API Response Content: {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Monday API request failed: {e}")
        if response:
            logger.error(f"Response content: {response.text}")
        raise

def get_subitems_by_group_and_name(group_id, item_name):
    """
    Retrieve subitems from a specific group where item name matches parent item name
    """
    # Use the specific board ID provided
    board_id = "9431708170"
    
    query = f"""
    query {{
        boards(ids: {board_id}) {{
            items_page(limit: 50, query_params: {{rules: [{{column_id: "group", compare_value: ["{group_id}"], operator: any_of}}]}}) {{
                items {{
                    id
                    name
                    group {{
                        id
                        title
                    }}
                    subitems {{
                        id
                        name
                        board {{
                            id
                        }}
                        column_values {{
                            id
                            value
                            text
                        }}
                    }}
                }}
            }}
        }}
    }}
    """
    
    response = make_monday_api_request(query)
    
    # Extract subitems from response
    subitems = []
    try:
        for board in response.get("data", {}).get("boards", []):
            items_page = board.get("items_page", {})
            for item in items_page.get("items", []):
                if item.get("name") == item_name:
                    item_subitems = item.get("subitems", [])
                    logger.info(f"Found {len(item_subitems)} subitems for item {item_name}")
                    subitems.extend(item_subitems)
                    
        # If no exact match found, log available items for debugging
        if not subitems:
            logger.info("Available items in the group:")
            for board in response.get("data", {}).get("boards", []):
                items_page = board.get("items_page", {})
                for item in items_page.get("items", []):
                    logger.info(f"  - {item.get('name')} (subitems: {len(item.get('subitems', []))})")
                    
    except Exception as e:
        logger.error(f"Error parsing subitems response: {e}")
    
    return subitems

def get_item_data(item_id, item_name):
    """
    Get item data with required columns from Monday.com
    """
    board_id = "9431708170"
    
    query = f"""
    query {{
        items(ids: [{item_id}]) {{
            id
            name
            column_values(ids: ["numeric_mks63qc1", "numeric_mks64nh2", "color_mks7xywc", "numeric_mks61nvq"]) {{
                id
                value
            }}
        }}
    }}
    """
    
    response = make_monday_api_request(query)
    
    # Extract item data from response
    item_data = {
        "id": item_id,
        "name": item_name,
        "numeric_mks63qc1": 0,
        "numeric_mks64nh2": 0,
        "color_mks7xywc": "",
        "numeric_mks61nvq": 0
    }
    
    try:
        items = response.get("data", {}).get("items", [])
        if items:
            item = items[0]
            for col in item.get("column_values", []):
                if col["id"] == "numeric_mks63qc1":
                    try:
                        # Monday.com returns numeric values as quoted strings
                        value_str = col["value"] or "0"
                        # Remove quotes if present
                        if value_str.startswith('"') and value_str.endswith('"'):
                            value_str = value_str[1:-1]
                        item_data["numeric_mks63qc1"] = float(value_str)
                    except (ValueError, TypeError):
                        item_data["numeric_mks63qc1"] = 0
                elif col["id"] == "numeric_mks64nh2":
                    try:
                        value_str = col["value"] or "0"
                        if value_str.startswith('"') and value_str.endswith('"'):
                            value_str = value_str[1:-1]
                        item_data["numeric_mks64nh2"] = float(value_str)
                    except (ValueError, TypeError):
                        item_data["numeric_mks64nh2"] = 0
                elif col["id"] == "color_mks7xywc":
                    item_data["color_mks7xywc"] = col["value"] or ""
                elif col["id"] == "numeric_mks61nvq":
                    try:
                        value_str = col["value"] or "0"
                        if value_str.startswith('"') and value_str.endswith('"'):
                            value_str = value_str[1:-1]
                        item_data["numeric_mks61nvq"] = float(value_str)
                    except (ValueError, TypeError):
                        item_data["numeric_mks61nvq"] = 0
    except Exception as e:
        logger.error(f"Error parsing item data response: {e}")
    
    return item_data

def update_subitem_column(subitem_id, column_id, value, subitem_board_id="9431861361"):
    """
    Update a specific column value for a subitem
    """
    # Subitems are updated using the standard change_column_value mutation with their board_id
    query = """
    mutation($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
        change_column_value(board_id: $boardId, item_id: $itemId, column_id: $columnId, value: $value) {
            id
        }
    }
    """
    
    variables = {
        "boardId": str(subitem_board_id),
        "itemId": str(subitem_id),
        "columnId": column_id,
        "value": str(value)
    }
    
    return make_monday_api_request(query, variables)

def duplicate_subitem(subitem_id, new_name):
    """
    Duplicate a subitem with a new name
    """
    query = """
    mutation($boardId: ID!, $itemId: ID!) {
        duplicate_item(board_id: $boardId, item_id: $itemId) {
            id
        }
    }
    """
    
    variables = {
        "boardId": "9431861361",  # Subitem board ID
        "itemId": str(subitem_id)
    }
    
    response = make_monday_api_request(query, variables)
    
    # Update the name of the duplicated item
    if response.get("data", {}).get("duplicate_item", {}).get("id"):
        new_item_id = response["data"]["duplicate_item"]["id"]
        
        # Update name using change_simple_column_value for name column
        update_query = """
        mutation($boardId: ID!, $itemId: ID!, $value: String!) {
            change_simple_column_value(board_id: $boardId, item_id: $itemId, column_id: "name", value: $value) {
                id
            }
        }
        """
        
        update_variables = {
            "boardId": "9431861361",  # Subitem board ID
            "itemId": str(new_item_id),
            "value": new_name
        }
        
        make_monday_api_request(update_query, update_variables)
        logger.info(f"Duplicated subitem {subitem_id} -> {new_item_id} with name '{new_name}'")
        return new_item_id
    
    return None

def delete_item(item_id, board_id="9431861361"):
    """
    Delete an item from Monday.com
    """
    query = """
    mutation($itemId: ID!) {
        delete_item(item_id: $itemId) {
            id
        }
    }
    """
    
    variables = {
        "itemId": str(item_id)
    }
    
    response = make_monday_api_request(query, variables)
    
    if response.get("data", {}).get("delete_item", {}).get("id"):
        logger.info(f"Successfully deleted item {item_id}")
        return True
    else:
        logger.error(f"Failed to delete item {item_id}")
        return False

def distribute_values(item_data):
    """
    Main logic for distributing values across subitems
    """
    try:
        # Extract data from payload
        numeric_value = float(item_data.get("numeric_mks63qc1", 0))
        formula_value = float(item_data.get("numeric_mks64nh2", 0))
        currency_dropdown = item_data.get("color_mks7xywc", "")
        limit_value = float(item_data.get("numeric_mks61nvq", 0))
        item_name = item_data.get("name", "")
        item_id = item_data.get("id", "")
        
        logger.info(f"Processing item: {item_name} (ID: {item_id})")
        logger.info(f"Values - Numeric: {numeric_value}, Formula: {formula_value}, Currency: {currency_dropdown}, Limit: {limit_value}")
        
        # Determine group based on currency - handle both text and JSON ID formats
        group_id = "group_mks6z9xe"  # Both currencies use the same group
        
        # Check if we have a valid currency dropdown value
        valid_currency = False
        if currency_dropdown in ["$ DÓLAR", "€ EURO"]:
            valid_currency = True
        elif currency_dropdown in ['{"ids":[1]}', '{"ids":[2]}', '{"ids":[3]}', '{"ids":[4]}']:
            # Monday.com JSON format - any of these IDs are valid for processing
            valid_currency = True
        else:
            # Try to parse JSON format to check for dropdown IDs (Monday.com format)
            try:
                parsed_dropdown = json.loads(currency_dropdown)
                if "ids" in parsed_dropdown and isinstance(parsed_dropdown["ids"], list):
                    # Accept any dropdown with valid IDs - both Dollar (ID 1) and Euro (IDs 2,3,4) are valid
                    valid_ids = [1, 2, 3, 4]  # 1 for Dollar, 2-4 for Euro variations
                    if any(id_val in valid_ids for id_val in parsed_dropdown["ids"]):
                        valid_currency = True
                        logger.info(f"Accepted currency dropdown with IDs: {parsed_dropdown['ids']}")
            except (json.JSONDecodeError, TypeError):
                # If it's not JSON, check if it contains Euro text
                if "EURO" in currency_dropdown.upper() or "€" in currency_dropdown:
                    valid_currency = True
        
        if not valid_currency:
            logger.error(f"Invalid currency dropdown value: {currency_dropdown}")
            return {"error": "Invalid currency dropdown value"}, 400
        
        # Get subitems from the parent item with same name in group_mks6z9xe
        logger.info(f"Looking for parent item '{item_name}' in group '{group_id}' to get its subitems")
        subitems = get_subitems_by_group_and_name(group_id, item_name)
        
        if not subitems:
            logger.warning(f"No subitems found for parent item '{item_name}' in group '{group_id}'")
            return {"message": f"No subitems found for parent item '{item_name}' in group '{group_id}'"}, 200
        
        # Debug: Log detailed information about the first few subitems to understand the data structure
        logger.debug(f"Total subitems found: {len(subitems)}")
        for i, subitem in enumerate(subitems[:3]):  # Log first 3 subitems
            logger.debug(f"Subitem {i+1} ({subitem.get('name')}): {json.dumps(subitem, indent=2)}")
        
        # Find the next eligible subitem with empty numeric_mks6p0bv to start processing
        # Valid dropdown text values for eligible "tipo" values
        valid_dropdown_texts = [
            "Parte Terrestre Internacional",
            "Parte Aérea Internacional"
        ]
        
        # Find the starting point - first subitem with empty numeric_mks6p0bv and eligible tipo
        start_index = None
        eligible_subitems = []
        
        for i, subitem in enumerate(subitems):
            dropdown_text = None
            numeric_mks6p0bv_value = 0
            
            for col in subitem.get("column_values", []):
                if col["id"] == "dropdown_mks6gqg0":
                    dropdown_text = col.get("text", "")
                elif col["id"] == "numeric_mks6p0bv":
                    try:
                        value_str = col["value"] or "0"
                        if value_str.startswith('"') and value_str.endswith('"'):
                            value_str = value_str[1:-1]
                        numeric_mks6p0bv_value = float(value_str)
                    except (ValueError, TypeError):
                        numeric_mks6p0bv_value = 0
            
            # Check if subitem has eligible tipo and is empty
            if dropdown_text in valid_dropdown_texts:
                eligible_subitems.append({
                    'subitem': subitem,
                    'index': i,
                    'is_empty': numeric_mks6p0bv_value == 0,
                    'dropdown_text': dropdown_text
                })
                
                # Mark the first empty eligible subitem as starting point
                if numeric_mks6p0bv_value == 0 and start_index is None:
                    start_index = i
                    logger.info(f"Found starting point at subitem {subitem.get('name')} (index {i}) with tipo: {dropdown_text}")
        
        if not eligible_subitems:
            logger.warning("No subitems found with eligible tipo values")
            return {"message": "No subitems found with eligible tipo values"}, 200
        
        # Log all eligible subitems found for debugging
        logger.info(f"Found {len(eligible_subitems)} eligible subitems:")
        for item in eligible_subitems:
            status = "empty" if item['is_empty'] else "processed"
            logger.info(f"  - '{item['subitem']['name']}' (index {item['index']}): {status} - tipo: {item['dropdown_text']}")
        
        if start_index is None:
            logger.info("All eligible subitems already processed")
            
            # Log detailed status for debugging
            status_summary = {}
            for item in eligible_subitems:
                status = "processed" if not item['is_empty'] else "empty"
                if status not in status_summary:
                    status_summary[status] = 0
                status_summary[status] += 1
                logger.info(f"Subitem '{item['subitem']['name']}' (index {item['index']}): {status} - tipo: {item['dropdown_text']}")
            
            logger.info(f"Eligible subitems status: {status_summary}")
            return {
                "message": "All eligible subitems already processed", 
                "status_summary": status_summary,
                "total_eligible": len(eligible_subitems)
            }, 200
        
        # Get all empty eligible subitems to process
        unprocessed_subitems = [item['subitem'] for item in eligible_subitems if item['is_empty']]
        
        logger.info(f"Starting distribution from index {start_index}, found {len(unprocessed_subitems)} empty eligible subitems to process")
        
        # Distribute values across multiple subitems using sequential remainder logic
        # Use limit_value (numeric_mks61nvq) as the total amount to distribute
        remaining_value = limit_value
        processed_subitems = []
        
        # Determine deduction column based on currency
        deduction_column = "numeric_mks6ywg8"  # Default to Euro column
        
        # Check if currency is Dollar to use the other column
        is_dollar = False
        if currency_dropdown == "$ DÓLAR":
            is_dollar = True
        elif currency_dropdown.startswith('{"ids":[2]') or currency_dropdown.startswith('{"ids":[3]') or currency_dropdown.startswith('{"ids":[4]'):
            # IDs 2, 3, 4 are Dollar variants in this Monday.com dropdown
            is_dollar = True
        
        # ID 1 is Euro, so we keep the default deduction_column = "numeric_mks6ywg8"
        if is_dollar:
            deduction_column = "numeric_mks6myhs"
        
        logger.info(f"Starting sequential distribution from total {remaining_value} across {len(unprocessed_subitems)} eligible subitems")
        logger.info(f"Will copy numeric_mks63qc1 value ({numeric_value}) to each subitem's numeric_mks6p0bv")
        logger.info(f"Using deduction column: {deduction_column} for currency: {currency_dropdown} (is_dollar: {is_dollar})")
        
        for subitem in unprocessed_subitems:
            if remaining_value <= 0:
                logger.info("No remaining value to distribute, stopping")
                break
            
            # Get subitem deduction value from the appropriate column based on currency
            subitem_deduction_value = 0
            logger.debug(f"Subitem {subitem.get('name')} column values: {[{col['id']: col['value']} for col in subitem.get('column_values', [])]}")
            for col in subitem.get("column_values", []):
                if col["id"] == deduction_column:
                    try:
                        # Monday.com returns numeric values as quoted strings, so we need to parse them
                        raw_value = col["value"] or "0"
                        # Remove quotes if present
                        clean_value = raw_value.strip('"') if isinstance(raw_value, str) else str(raw_value)
                        subitem_deduction_value = float(clean_value)
                        logger.debug(f"Found {deduction_column} value: {col['value']} -> {subitem_deduction_value}")
                    except (ValueError, TypeError):
                        subitem_deduction_value = 0
                        logger.debug(f"Could not parse {deduction_column} value: {col['value']}")
                    break
            
            # Process if there's a deduction value
            if subitem_deduction_value > 0:
                # Get the subitem's board ID
                subitem_board_id = subitem.get("board", {}).get("id", "9431861361")
                
                # Check if remaining value is enough to cover the full deduction
                if remaining_value >= subitem_deduction_value:
                    # Normal processing - remaining value covers the deduction
                    update_subitem_column(subitem["id"], "numeric_mks6p0bv", numeric_value, subitem_board_id)
                    remaining_value -= subitem_deduction_value
                    
                    processed_subitems.append({
                        "id": subitem["id"],
                        "name": subitem["name"],
                        "assigned_value": numeric_value,
                        "deducted_value": subitem_deduction_value
                    })
                    
                    logger.info(f"Processed subitem {subitem['name']}: copied {numeric_value} to numeric_mks6p0bv, deducted {subitem_deduction_value} from remaining, new remaining: {remaining_value}")
                
                else:
                    # Remaining value is not enough - need to duplicate and split
                    logger.info(f"Remaining value {remaining_value} is not enough for subitem {subitem['name']} deduction {subitem_deduction_value}")
                    
                    # Duplicate the subitem to create Part 1 first, then Part 2 (so Part 1 appears on top)
                    part1_id = duplicate_subitem(subitem["id"], f"{subitem['name']} Parte 1")
                    part2_id = duplicate_subitem(subitem["id"], f"{subitem['name']} Parte 2")
                    
                    if part1_id and part2_id:
                        # Part 1 gets the remaining value in the appropriate deduction column and gets processed
                        update_subitem_column(part1_id, deduction_column, remaining_value, subitem_board_id)
                        update_subitem_column(part1_id, "numeric_mks6p0bv", numeric_value, subitem_board_id)
                        
                        # Part 2 gets the difference in the appropriate deduction column (not processed yet)
                        part2_deduction = subitem_deduction_value - remaining_value
                        update_subitem_column(part2_id, deduction_column, part2_deduction, subitem_board_id)
                        
                        # Delete the original subitem after creating the duplicates
                        if delete_item(subitem["id"], subitem_board_id):
                            logger.info(f"Deleted original subitem {subitem['name']} (ID: {subitem['id']})")
                        
                        processed_subitems.append({
                            "id": part1_id,
                            "name": f"{subitem['name']} Parte 1",
                            "assigned_value": numeric_value,
                            "deducted_value": remaining_value
                        })
                        
                        processed_subitems.append({
                            "id": part2_id,
                            "name": f"{subitem['name']} Parte 2",
                            "assigned_value": 0,  # Not processed yet
                            "deducted_value": part2_deduction
                        })
                        
                        logger.info(f"Created {subitem['name']} Parte 1 and Parte 2")
                        logger.info(f"Parte 1: {deduction_column}={remaining_value}, numeric_mks6p0bv={numeric_value}")
                        logger.info(f"Parte 2: {deduction_column}={part2_deduction}")
                        
                        # Set remaining to 0 since we've used it all
                        remaining_value = 0
                        break
                    else:
                        logger.error(f"Failed to duplicate subitem {subitem['name']}")
                        break
            else:
                logger.info(f"Skipped subitem {subitem.get('name')}: deduction_value={subitem_deduction_value}, remaining={remaining_value}")
        
        
        
        # Store operation state
        operation_state[item_id] = {
            "timestamp": datetime.now().isoformat(),
            "processed_subitems": processed_subitems,
            "remaining_value": remaining_value
        }
        
        return {
            "message": "Values distributed successfully",
            "processed_subitems": processed_subitems,
            "remaining_value": remaining_value
        }, 200
        
    except Exception as e:
        logger.error(f"Error in distribute_values: {e}")
        return {"error": str(e)}, 500

@app.route('/')
def index():
    """Main page with webhook information"""
    return render_template('index.html')

@app.route('/status')
def status():
    """Status page showing recent operations"""
    return render_template('status.html', operations=operation_state)

@app.route('/test-api')
def test_api():
    """Test Monday.com API connection"""
    try:
        # Simple query to test API connection
        test_query = """
        query {
            me {
                id
                name
                email
            }
        }
        """
        
        response = make_monday_api_request(test_query)
        return jsonify({
            "status": "success",
            "response": response
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/explore-board')
def explore_board():
    """Explore board structure"""
    try:
        # Query to get items from a specific group - correct syntax
        explore_query = """
        query {
            boards(ids: 9431708170) {
                id
                name
                items_page(limit: 10, query_params: {rules: [{column_id: "group", compare_value: ["group_mks6z9xe"], operator: any_of}]}) {
                    items {
                        id
                        name
                        group {
                            id
                            title
                        }
                        subitems {
                            id
                            name
                            column_values {
                                id
                                value
                            }
                        }
                    }
                }
            }
        }
        """
        
        response = make_monday_api_request(explore_query)
        return jsonify({
            "status": "success",
            "response": response
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/distribuir', methods=['POST'])
def distribuir():
    """
    Main webhook endpoint for Monday.com payloads
    """
    try:
        # Validate request
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({"error": "Request must be JSON"}), 400
        
        payload = request.get_json()
        
        if not payload:
            logger.error("Empty payload received")
            return jsonify({"error": "Empty payload"}), 400
        
        # Handle Monday.com challenge verification
        if 'challenge' in payload:
            logger.info("Received Monday.com challenge verification")
            challenge = payload['challenge']
            return jsonify({'challenge': challenge})
        
        logger.info(f"Received webhook payload: {json.dumps(payload, indent=2)}")
        
        # Extract basic info from Monday.com webhook payload
        item_id = None
        item_name = None
        
        # Handle Monday.com webhook format
        if "event" in payload and "pulseId" in payload["event"]:
            item_id = payload["event"]["pulseId"]
            item_name = payload["event"].get("pulseName", "")
        elif "event" in payload and "data" in payload["event"]:
            # Current webhook format with nested data
            event_data = payload["event"]["data"]
            item_id = event_data.get("item_id", "")
            item_name = event_data.get("item_name", "")
        elif "item" in payload:
            # Alternative format or testing
            item_id = payload["item"].get("id", "")
            item_name = payload["item"].get("name", "")
        else:
            # Direct format for testing
            item_id = payload.get("id", "")
            item_name = payload.get("name", "")
        
        if not item_id or not item_name:
            logger.error("Could not extract item ID or name from webhook payload")
            return jsonify({"error": "Invalid webhook payload"}), 400
        
        # Query Monday.com to get the actual item data with required columns
        item_data = get_item_data(item_id, item_name)
        
        if not item_data:
            logger.error("Could not retrieve item data from Monday.com")
            return jsonify({"error": "Could not retrieve item data"}), 400
        
        # Validate that we have the required data (status column must have a value)
        if not item_data.get("color_mks7xywc"):
            logger.info(f"Item {item_name} has no status value set, skipping processing")
            return jsonify({"message": "No status value set, skipping processing"}), 200
        
        if item_data.get("numeric_mks63qc1", 0) <= 0:
            logger.info(f"Item {item_name} has no value to distribute")
            return jsonify({"message": "No value to distribute"}), 200
        
        # Process the distribution
        result, status_code = distribute_values(item_data)
        
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Unexpected error in webhook endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # For local development
    app.run(host='0.0.0.0', port=5000, debug=True)

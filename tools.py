import json
import random
import string
from datetime import datetime
from database import save_booking, save_customer, get_customer_bookings

# --- Tool Definitions (schemas that tell the LLM what tools exist) ---

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_service_area",
            "description": "Check if a given city or zip code is within Pinnacle Home Services' service area. Call this whenever a customer provides their address or location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "The city name, e.g. 'Round Rock'"
                    },
                    "zip_code": {
                        "type": "string",
                        "description": "The zip code, e.g. '78701'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_estimate",
            "description": "Get a rough price estimate for a specific service. Call this when the customer describes their issue and you need to provide pricing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_category": {
                        "type": "string",
                        "enum": ["plumbing", "electrical", "hvac"],
                        "description": "The category of service needed"
                    },
                    "job_type": {
                        "type": "string",
                        "description": "Brief description of the job, e.g. 'leaky faucet', 'outlet repair', 'AC not cooling'"
                    }
                },
                "required": ["service_category", "job_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a service appointment once all customer details have been collected. Only call this when you have the customer's name, address, phone, service needed, and preferred date/time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Full name of the customer"
                    },
                    "address": {
                        "type": "string",
                        "description": "Full service address"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Customer phone number"
                    },
                    "service_category": {
                        "type": "string",
                        "enum": ["plumbing", "electrical", "hvac"],
                        "description": "The category of service"
                    },
                    "issue_description": {
                        "type": "string",
                        "description": "Description of the issue"
                    },
                    "preferred_date": {
                        "type": "string",
                        "description": "Preferred date for service, e.g. '2025-10-15'"
                    },
                    "preferred_time": {
                        "type": "string",
                        "description": "Preferred time window, e.g. 'morning', 'afternoon', '10am-12pm'"
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["routine", "soon", "emergency"],
                        "description": "How urgent the service is"
                    }
                },
                "required": ["customer_name", "address", "phone", "service_category", "issue_description", "preferred_date", "preferred_time", "urgency"]
            }
        }
    }
    ,
    {
        "type": "function",
        "function": {
            "name": "lookup_customer",
            "description": "Look up a customer by phone number to check if they are a returning customer. Call this when a customer provides their phone number to see if they have previous bookings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "The customer's phone number"
                    }
                },
                "required": ["phone"]
            }
        }
    }
]


# --- Tool Implementations (the actual logic that runs) ---

# Valid service area zip codes and cities
SERVICE_AREA_ZIPS = {
    "78701", "78702", "78703", "78704", "78705", "78712", "78717", "78719",
    "78721", "78722", "78723", "78724", "78725", "78726", "78727", "78728",
    "78729", "78730", "78731", "78732", "78733", "78734", "78735", "78736",
    "78737", "78738", "78739", "78741", "78742", "78744", "78745", "78746",
    "78747", "78748", "78749", "78750", "78751", "78752", "78753", "78754",
    "78756", "78757", "78758", "78759",
    "78660",  # Pflugerville
    "78664", "78665",  # Round Rock
    "78613",  # Cedar Park
    "78626", "78628", "78633",  # Georgetown
    "78666",  # San Marcos
    "78640",  # Kyle
    "78610",  # Buda
    "78734", "78738",  # Lakeway
    "78738",  # Bee Cave
    "78620",  # Dripping Springs
}

SERVICE_AREA_CITIES = {
    "austin", "round rock", "cedar park", "pflugerville", "georgetown",
    "san marcos", "kyle", "buda", "lakeway", "bee cave", "dripping springs"
}

PRICING = {
    "plumbing": {
        "leaky faucet": {"low": 100, "high": 200},
        "faucet repair": {"low": 100, "high": 200},
        "toilet repair": {"low": 150, "high": 300},
        "toilet": {"low": 150, "high": 300},
        "drain cleaning": {"low": 150, "high": 300},
        "clogged drain": {"low": 150, "high": 300},
        "water heater repair": {"low": 200, "high": 500},
        "water heater replacement": {"low": 1200, "high": 3000},
        "pipe repair": {"low": 200, "high": 600},
        "burst pipe": {"low": 200, "high": 600},
        "sewer line": {"low": 1000, "high": 5000},
    },
    "electrical": {
        "outlet repair": {"low": 100, "high": 200},
        "switch repair": {"low": 100, "high": 200},
        "light fixture": {"low": 150, "high": 350},
        "light installation": {"low": 150, "high": 350},
        "circuit breaker": {"low": 200, "high": 400},
        "panel upgrade": {"low": 1500, "high": 3000},
        "rewiring": {"low": 8000, "high": 15000},
    },
    "hvac": {
        "ac tune-up": {"low": 100, "high": 200},
        "ac tuneup": {"low": 100, "high": 200},
        "ac repair": {"low": 200, "high": 600},
        "ac not cooling": {"low": 200, "high": 600},
        "furnace repair": {"low": 200, "high": 500},
        "no heat": {"low": 200, "high": 500},
        "ac replacement": {"low": 3500, "high": 7000},
        "hvac replacement": {"low": 7000, "high": 15000},
    }
}


def check_service_area(city=None, zip_code=None):
    """Check if a location is within the service area."""
    if zip_code and zip_code in SERVICE_AREA_ZIPS:
        return {"in_service_area": True, "message": f"Zip code {zip_code} is within our service area."}

    if city and city.lower().strip() in SERVICE_AREA_CITIES:
        return {"in_service_area": True, "message": f"{city} is within our service area."}

    location = zip_code or city or "Unknown"
    return {"in_service_area": False, "message": f"Sorry, {location} is outside our service area. We serve Austin, TX and surrounding areas within 30 miles."}


def get_price_estimate(service_category, job_type):
    """Look up pricing for a given service."""
    category_pricing = PRICING.get(service_category.lower(), {})

    # Try to find a matching job type (fuzzy matching by checking if key is in the job description)
    job_lower = job_type.lower()
    for key, price_range in category_pricing.items():
        if key in job_lower or job_lower in key:
            return {
                "found": True,
                "service_category": service_category,
                "job_type": job_type,
                "estimate_low": price_range["low"],
                "estimate_high": price_range["high"],
                "note": "This is a rough estimate. Exact pricing will be determined after an on-site assessment."
            }

    # No exact match found
    return {
        "found": False,
        "service_category": service_category,
        "job_type": job_type,
        "message": f"We don't have standard pricing for '{job_type}'. A technician will provide a quote during the on-site assessment.",
        "note": "We can still book an appointment for an assessment."
    }


def book_appointment(customer_name, address, phone, service_category, issue_description, preferred_date, preferred_time, urgency):
    """Book a service appointment and return a confirmation number."""
    conf_number = "PHS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    booking = {
        "confirmation_number": conf_number,
        "customer_name": customer_name,
        "address": address,
        "phone": phone,
        "service_category": service_category,
        "issue_description": issue_description,
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
        "urgency": urgency,
        "status": "confirmed",
        "booked_at": datetime.now().isoformat(),
        "message": f"Appointment booked successfully! Confirmation number: {conf_number}. A team member will call {phone} within 1 business hour to confirm the details."
    }

    # Save to database
    save_booking(booking)
    save_customer(customer_name, phone, address)

    return booking


def lookup_customer(phone):
    """Look up a customer and their booking history."""
    from database import get_customer
    customer = get_customer(phone)
    if not customer:
        return {"found": False, "message": "No existing customer found with this phone number."}

    bookings = get_customer_bookings(phone)
    return {
        "found": True,
        "customer": customer,
        "previous_bookings": bookings,
        "message": f"Returning customer: {customer['name']}. They have {len(bookings)} previous booking(s)."
    }


# Map function names to their implementations
TOOL_FUNCTIONS = {
    "check_service_area": check_service_area,
    "get_price_estimate": get_price_estimate,
    "book_appointment": book_appointment,
    "lookup_customer": lookup_customer,
}


def execute_tool(function_name, arguments):
    """Execute a tool by name with the given arguments."""
    func = TOOL_FUNCTIONS.get(function_name)
    if not func:
        return {"error": f"Unknown tool: {function_name}"}

    args = json.loads(arguments) if isinstance(arguments, str) else arguments
    return func(**args)

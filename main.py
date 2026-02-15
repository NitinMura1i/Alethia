import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from prompts import SYSTEM_PROMPT
from tools import TOOLS, execute_tool
from database import init_db, save_message, get_conversation_history

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def chat(conversation_history, customer_phone=None):
    """Send the conversation to the LLM and get a response.

    Handles the tool-calling loop: if the model wants to call a tool,
    we execute it, feed the result back, and let the model continue.
    """
    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conversation_history,
            tools=TOOLS,
            temperature=0.7,
        )

        message = response.choices[0].message

        # If no tool calls, we're done — return the text response
        if not message.tool_calls:
            msg = {"role": "assistant", "content": message.content}
            conversation_history.append(msg)
            if customer_phone:
                save_message(customer_phone, msg)
            return message.content

        # The model wants to call one or more tools
        assistant_msg = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in message.tool_calls
            ]
        }
        conversation_history.append(assistant_msg)
        if customer_phone:
            save_message(customer_phone, assistant_msg)

        # Execute each tool call and add results to history
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            arguments = tool_call.function.arguments

            print(f"  [Tool Call: {function_name}({arguments})]")

            result = execute_tool(function_name, arguments)

            print(f"  [Tool Result: {json.dumps(result)}]")

            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            }
            conversation_history.append(tool_msg)
            if customer_phone:
                save_message(customer_phone, tool_msg)

        # Loop back — the model will now generate a response using the tool results


def main():
    # Initialize database on startup
    init_db()

    print("=" * 50)
    print("  Pinnacle Home Services - Virtual Assistant")
    print("=" * 50)
    print("Type 'quit' to exit.\n")

    # Ask for phone number to identify the customer
    customer_phone = input("Please enter your phone number: ").strip()

    if not customer_phone:
        print("Phone number is required. Goodbye!")
        return

    # Initialize conversation with the system prompt
    conversation_history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # Check if this is a returning customer by loading past conversation
    past_messages = get_conversation_history(customer_phone)
    if past_messages:
        print(f"\n  [Returning customer detected - loading {len(past_messages)} previous messages]\n")
        # Add a summary context message so the agent knows about the history
        history_summary = {"role": "system", "content": (
            "The following messages are from a previous conversation with this customer. "
            "Use this context to provide a more personalized experience. "
            "Welcome them back and reference their past interactions if relevant."
        )}
        conversation_history.append(history_summary)
        conversation_history.extend(past_messages)

    # Get the agent's opening greeting
    greeting = chat(conversation_history, customer_phone)
    print(f"Agent: {greeting}\n")

    # Main conversation loop
    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("\nThanks for contacting Pinnacle Home Services. Goodbye!")
            break

        # Add user message to history and save to database
        user_msg = {"role": "user", "content": user_input}
        conversation_history.append(user_msg)
        save_message(customer_phone, user_msg)

        # Get agent response (may involve tool calls)
        response = chat(conversation_history, customer_phone)

        print(f"\nAgent: {response}\n")

if __name__ == "__main__":
    main()

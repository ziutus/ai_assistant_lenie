import json
import os
import copy

from dotenv import load_dotenv
from pprint import pprint

from library.ai import ai_ask

load_dotenv()

# Read JSON file
file_path = "../tmp/json.json"

API_KEY = os.environ.get('AI_DEV3_API_KEY')

def calculate_from_string(question: str):
    try:
        # Split the string by spaces
        tokens = question.split()
        if len(tokens) != 3:
            raise ValueError(f"Invalid question format: {question}. Expected format: 'number operator number'.")

        # Parse numbers and operator
        num1 = int(tokens[0])
        operator = tokens[1]
        num2 = int(tokens[2])

        # Perform the operation based on the operator
        if operator == '+':
            return num1 + num2
        elif operator == '-':
            return num1 - num2
        elif operator == '*':
            return num1 * num2
        elif operator == '/':
            if num2 == 0:
                raise ValueError("Division by zero is not allowed.")
            return num1 / num2
        else:
            raise ValueError(f"Unsupported operator: {operator}. Supported operators are: +, -, *, /")

    except ValueError as e:
        return str(e)

try:
    with open(file_path, "r") as file:
        data = json.load(file)
        # print(data)
except FileNotFoundError:
    print(f"The file '{file_path}' was not found.")
except json.JSONDecodeError:
    print(f"Error decoding JSON from the file '{file_path}'.")

json_target = copy.deepcopy(data)
json_target["apikey"] = API_KEY
json_target["test-data"] = []

for entry in data['test-data']:
    if isinstance(entry, dict) and 'question' in entry.keys() and 'answer' in entry.keys():
        # print("Valid entry:", entry)
        entry_target = copy.deepcopy(entry)
        answer_from_string = calculate_from_string(entry['question'])
        if answer_from_string == entry['answer']:
            # print("Correct answer!, no action needed...")
            pass
        else:
            # print(entry)
            # print(f"Wrong answer, correct: {answer_from_string}, got: {entry['answer']}.")
            entry_target["answer"] = answer_from_string

        if 'test' in entry.keys():
            pprint(entry['test'])
            print(f"Need found answer to question: {entry['test']['q']}")

            question_with_instruction = f"""
            Na pytanie należy odpowiedzieć w języku anglielskim. Odpowiedz tylko na pytanie. Nie dodawaj żadnego komentarza.
            Pytanie: {entry['test']['q']}

            """

            ai_answer = ai_ask(question_with_instruction, model="amazon.nova-micro", temperature=0)
            # ai_answer = ai_ask(question_with_instruction, model="amazon.titan-tg1-large")
            pprint(ai_answer.response_text)
            entry_target['test']['a'] = ai_answer.response_text

        json_target["test-data"].append(entry_target)

    else:
        print(f"Invalid entry format, found extra data: {entry}")


# pprint(json_target)

output_file_path = "../tmp/json_answer.json"

try:
    with open(output_file_path, "w") as output_file:
        json.dump(json_target, output_file, indent=4)
    print(f"Data successfully written to {output_file_path}.")
except IOError as e:
    print(f"An error occurred while writing to the file: {e}")

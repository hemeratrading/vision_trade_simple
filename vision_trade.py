from multiprocessing import Process
import os
import sys
import requests
import base64
import mysql.connector
from dotenv import load_dotenv
import json
import re



# Učitaj .env fajl
load_dotenv('/var/keys/.env')
openAIKeys = os.getenv('openAI')
model = "gpt-4o"

def clean_number_format(json_str):
    cleaned_str = json_str.replace(',', '')
    return cleaned_str

config = {
    'user': 'doadmin',
    'password': os.getenv('DB_PASS'),
    'host': 'hemera-db-mysql-do-user-12096206-0.b.db.ondigitalocean.com',
    'port': 25060,
    'database': 'hemera'
}

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def reduce_usage_by_one(username, config):
    try:
        with mysql.connector.connect(**config) as conn, conn.cursor() as cursor:
            sql = f"UPDATE gpt4turbo SET total_usage = total_usage - 1 WHERE username = '{username}'"
            cursor.execute(sql)
            conn.commit()
    except mysql.connector.Error as error:
        print(f"Error updating total_usage: {error}")


def clean_number_formatting(content):
    content = re.sub(r'(\d+),(\d+)', r'\1\2', content)
    return content

def fix_decimal_format(content):
    content = re.sub(r'(\d+)\.(\d+)\.(\d+)', r'\1.\2\3', content)
    return content

def fix_json_format(content):
    content = content.replace('"\n"', '",\n"')
    content = content.replace(']\n"', '],\n"')
    return content


def convert_symbol(symbol):
    if '.' in symbol:
        symbol = symbol.split('.')[0]

    if symbol.endswith('USD'):
        symbol = symbol.replace('USD', 'USDT')

    return symbol








def main1(username, img):
    reduce_usage_by_one(username, config)
    global model

    base64_image = encode_image(img)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openAIKeys}"
    }

    common_text = f"""

     **IMPORTANT**: If the image does not contain any valid trading chart, trading symbol, or if the trading strategy cannot be determined (including Take Profit, Stop Loss, or Side), do not generate a JSON. Instead, return the error message: "Invalid input: Unable to determine valid trading chart, symbol, or strategy from the image.


    Analyze the following image and identify any cryptocurrency trading symbol or its full name.
    The symbol can appear in various formats such as 'BTCUSDT', 'BTCUSD.P', 'BTCUSD.D', or full names like 'Bitcoin / TetherUS', 'Ethereum', 'BitcoinCash', etc. 
    Convert any full names or non-standard formats to their respective ticker symbols. For example:
    - 'Bitcoin / TetherUS' should be converted to 'BTCUSDT'
    - 'Ethereum' should be converted to 'ETHUSDT'
    - 'BitcoinCash' should be converted to 'BCHUSDT'
    Always return the symbol in the format: '[TICKER]USDT'. If the image contains multiple symbols, return the most prominent one.


     ** Take Profits**: Must include at least one take-profit level, but can have more if the strategy supports it. Specify the percentage of the position to close at each TP level.
       - **Color and Line Style**: Take Profit levels are often marked with green lines or arrows. If you see a green line or arrow pointing to a price level, consider it as a potential Take Profit level. Ensure consistency between text and visual indications.
     ** Stop Loss (SL)**: Determine if there is a Stop Loss level indicated on the chart. Look for text labels such as 'SL', 'Stop Loss', or arrows/lines pointing to a specific price level. If the Stop Loss is labeled as 'Near Entry' or similar, consider the nearest support or resistance level for placing the Stop Loss. If no explicit SL is mentioned, infer an appropriate level based on the closest support zone below the entry point or recent swing low. Ensure consistency between text and visual indications. 
        - **Color and Line Style**: Stop Loss levels are often marked with red lines or arrows. If you see a red line or arrow pointing to a price level, consider it as a potential Stop Loss level. Ensure consistency between text and visual indications.
     ** Grid Levels**: Always leave this field empty.
     ** Order Types**:
        - Use **MARKET** order if the entry price is at the current market price without any specified price levels.
        - Use **LIMIT** orders only when specific entry price levels are clearly indicated and marked as potential entry points on the chart.
    Double-check all levels (Symbol, Entry Price, DCA Levels, Take Profits, and Stop Loss) to ensure they are precise and align with the overall strategy. If any of these levels are found to be inconsistent with the strategy, regenerate the strategy to ensure alignment.


        Analyze the provided image and return a JSON output formatted as follows:
        {{
            "Symbol": "TRADING_PAIR",
            "Side": "BUY/SELL",
            "Entry Price": ENTRY_PRICE (please use a single period for decimals),
            "Type": "LIMIT",  # Default is LIMIT unless Entry Price is 0, in which case it should be MARKET.
            "Take Profits": [
                TP1,
                TP2,
                TP3,
                ...
            ],
            "Stop Loss": SL,
            "Strategy Explanation": "Provide a brief explanation of the strategy behind the provided levels."
        }}
        Ensure all numbers are formatted with only one period (.) as the decimal separator. do not provide anything just JSON code, no ``` letters
    """

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": common_text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]
    }]

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 3700,
        "temperature": 0.2
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_data = response.json()

        for choice in response_data.get('choices', []):
            content = choice['message']['content'].strip()
            if not content:
                print("Error: Received empty response from OpenAI API")
                return


            cleaned_content = content.strip('```json').strip('```')

            cleaned_content = fix_decimal_format(cleaned_content)

            try:
                json_data = json.loads(cleaned_content)

                if json_data.get("Entry Price", 0) > 0:
                    json_data["Type"] = "LIMIT"

                strategy_explanation = json_data.pop("Strategy Explanation", "")
                json_data["Strategy Explanation"] = strategy_explanation

                json_data['Symbol'] = convert_symbol(json_data['Symbol'])

                print(json.dumps(json_data, indent=4))

            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON: {e}")
                print(f"Raw content: {cleaned_content}")

    except requests.exceptions.RequestException as e:
        print(f"Request to OpenAI API failed: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Missing arguments! Usage: vision_trade.py username img")
        sys.exit(1)

    username = sys.argv[1]
    img = sys.argv[2] if sys.argv[2] != 'None' else None

    p = Process(target=main1, args=(username, img))
    p.start()
    p.join()

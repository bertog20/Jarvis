import os
import json
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from openai import OpenAI
from pathlib import Path
import platform
from playsound import playsound  
from bs4 import BeautifulSoup
import requests
import re
import http.server
import socketserver
import threading
import webbrowser
import urllib.parse
import subprocess
import logging
import tldextract
import time
import pyautogui

# Set up logging
logging.basicConfig(level=logging.INFO)

# Path to Chrome on macOS
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome %s"
webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(chrome_path))

# OpenAI API setup
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Please set the OPENAI_API_KEY environment variable.")
client = OpenAI(api_key=api_key)

# Global variable to store scanned elements
stored_elements = None

def ask_jarvis(question):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error in ask_jarvis: {e}")
        return "Sorry, I encountered an error processing your request."

def summarize_text(text):
    """Summarize long text before sending it to text-to-speech."""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Summarize the following text for a visually impaired user in a formal tone."},
                {"role": "user", "content": text}
            ]
        )
        summary = response.choices[0].message.content
        logging.info(f"Generated summary: {summary[:100]}...")
        return summary
    except Exception as e:
        logging.error(f"Error summarizing text: {e}")
        return text[:4096]

def generate_formal_summary(url):
    """
    Fetches a snippet of the website's text and requests a formal summary
    describing its overall purpose and functionality (without listing interactive elements).
    """
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logging.error(f"Error fetching website, status code: {response.status_code}")
            return "Unable to fetch the website content for summarization."
        soup = BeautifulSoup(response.content, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if len(text) > 1000:
            text = text[:1000]
        prompt = ("Please provide a formal summary that describes the overall purpose and functionality of the website. "
                  "Do not list interactive elements such as buttons or links. Here is a snippet of the website content: " + text)
        summary = ask_jarvis(prompt)
        return summary
    except Exception as e:
        logging.error("Error generating formal summary: " + str(e))
        return "Unable to generate a formal summary for this website."

def speech_to_text(audio_path):
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        return transcript.text
    except Exception as e:
        logging.error(f"Error in speech_to_text: {e}")
        return ""

def text_to_speech(text, filename="speech.mp3"):
    print("Transcript:", text)
    logging.info("Transcript: " + text)
    try:
        if len(text) > 4096:
            logging.warning("Text too long. Summarizing before text-to-speech.")
            text = summarize_text(text)
        speech_file_path = Path(os.getcwd()) / filename
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy", 
            input=text
        )
        with open(speech_file_path, "wb") as f:
            f.write(response.content)
        logging.info(f"Speech saved to {speech_file_path}")
        play_audio(speech_file_path)
    except Exception as e:
        logging.error(f"Error in text_to_speech: {e}")

def play_audio(file_path):
    try:
        if platform.system() == "Darwin": 
            os.system(f"afplay {file_path}")
        elif platform.system() == "Windows":
            os.system(f'start {file_path}')
        elif platform.system() == "Linux":
            os.system(f"mpg123 {file_path}")
        else:
            playsound(str(file_path))
    except Exception as e:
        logging.error(f"Error in play_audio: {e}")

def record_audio(output_file="recorded.wav", record_seconds=5, fs=44100):
    try:
        logging.info("Recording...")
        audio_data = sd.rec(int(record_seconds * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()
        wav.write(output_file, fs, audio_data)
        logging.info("Finished recording")
        return output_file
    except Exception as e:
        logging.error(f"Error in record_audio: {e}")
        return None

def extract_url_from_text(text):
    match = re.search(r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text)
    if match:
        url = match.group(0)
        if not url.startswith("http"):
            url = "http://" + url
        return url
    lookup_match = re.search(r"look up ([a-zA-Z0-9.-]+)", text, re.IGNORECASE)
    if lookup_match:
        domain = lookup_match.group(1)
        extracted = tldextract.extract(domain)
        if extracted.suffix:
            url = f"http://{domain}"
            return url
    return None

def open_in_chrome(url):
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", "-a", "Google Chrome", url], check=True)
        elif platform.system() == "Windows":
            os.system(f"start chrome {url}")
        elif platform.system() == "Linux":
            os.system(f"google-chrome {url}")
        else:
            logging.error("Unsupported OS for opening Chrome.")
            return
        logging.info(f"Opened URL in Chrome: {url}")
    except Exception as e:
        logging.error(f"Error opening URL in Chrome: {e}")

def parse_search_inputs(url):
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logging.error(f"Error fetching website, status code: {response.status_code}")
            return []
        soup = BeautifulSoup(response.content, "html.parser")
        search_inputs = []
        for inp in soup.find_all("input"):
            if inp.get("type", "").lower() in ["text", "search"]:
                label = inp.get("placeholder") or inp.get("name") or "search"
                search_inputs.append(label)
        return search_inputs
    except Exception as e:
        logging.error(f"Error parsing search inputs: {e}")
        return []

def parse_buttons_and_links(url):
    try:
        response = requests.get(url)
        if response.status_code != 200:
            logging.error(f"Error fetching website, status code: {response.status_code}")
            return {"buttons": [], "links": []}
        soup = BeautifulSoup(response.content, "html.parser")
        buttons = [button.get_text(strip=True) for button in soup.find_all("button")]
        links = [link.get_text(strip=True) for link in soup.find_all("a") if link.get("href")]
        return {"buttons": buttons, "links": links}
    except Exception as e:
        logging.error(f"Error parsing website: {e}")
        return {"buttons": [], "links": []}

def simulate_typing_in_search(query):
    try:
        query_clean = query.strip()
        query_escaped = query_clean.replace('"', '\\"').replace("'", "\\'")
        script = (
            "var inputs = document.querySelectorAll('input[type=\"text\"], input[type=\"search\"]');"
            "if (inputs.length > 0) {"
            "inputs[0].value = '" + query_escaped + "';"
            "inputs[0].blur();"
            "}"
        )
        command = (
            'osascript -e "tell application \\"Google Chrome\\" to execute front window\'s active tab javascript \\"'
            + script + '\\""'
        )
        subprocess.run(command, shell=True)
        time.sleep(1)
        simulate_button_click("Search")
        logging.info(f"Simulated typing '{query_clean}' in the search box and clicking Search.")
    except Exception as e:
        logging.error(f"Error simulating typing in search: {e}")

def get_current_url():
    try:
        script = 'tell application "Google Chrome" to get URL of active tab of front window'
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        current_url = result.stdout.strip()
        logging.info(f"Current URL: {current_url}")
        return current_url
    except Exception as e:
        logging.error(f"Error getting current URL: {e}")
        return ""

def interactive_prompt(url):
    """
    Scans the webpage for interactive elements and asks the user a question.
    """
    time.sleep(3)  # Allow time for page updates
    search_fields = parse_search_inputs(url)
    if search_fields:
        prompt = "I see a search box. Would you like to type in the search box or press the 'Read Wikipedia in your language' button?"
    else:
        elements = parse_buttons_and_links(url)
        buttons = elements.get("buttons", [])
        links = elements.get("links", [])
        prompt = (f"The page shows the following buttons: {', '.join(buttons) if buttons else 'none'} and "
                  f"links: {', '.join(links) if links else 'none'}. Would you like to do something else?")
    text_to_speech(prompt)
    response_audio = record_audio("continue_response.wav", record_seconds=5)
    user_response = speech_to_text(response_audio).lower().strip()
    logging.info(f"User response for further action: {user_response}")
    return user_response

class JarvisHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/start"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            encoded_text = self.path[len("/start"):]
            decoded_text = urllib.parse.unquote(encoded_text)

            audio_file_path = record_audio("recorded.wav", record_seconds=5)
            if audio_file_path is None:
                self.wfile.write(b'{"error": "Recording failed"}')
                return

            spoken_text = speech_to_text(audio_file_path)
            url = extract_url_from_text(spoken_text)

            if url:
                logging.info(f"Looking up website: {url}")
                open_in_chrome(url)
                time.sleep(3)  # Allow website to load

                # Produce the initial formal summary of the website.
                formal_summary = generate_formal_summary(url)
                text_to_speech(formal_summary)

                # Then ask the interactive question.
                user_response = interactive_prompt(url)

                # Loop for continuous interaction.
                while user_response and not ("no" in user_response or "stop" in user_response):
                    search_match = re.search(r"(?:type|enter|look up)\s+(.+?)\s+(?:in(?: the)?\s+search\s+(?:box|input))", user_response)
                    if search_match:
                        query = search_match.group(1)
                        text_to_speech(f"Proceeding with search for '{query}'.")
                        simulate_typing_in_search(query)
                    elif "read wikipedia in your language" in user_response:
                        text_to_speech("Proceeding to click the 'Read Wikipedia in your language' button.")
                        simulate_button_click("Read Wikipedia in your language")
                    else:
                        text_to_speech("I did not understand your command. Please try again.")
                        user_response = interactive_prompt(url)
                        continue

                    time.sleep(3)
                    new_url = get_current_url()
                    if new_url:
                        url = new_url
                    # Instead of directly prompting for action, re‑generate the formal summary for the new page.
                    formal_summary = generate_formal_summary(url)
                    text_to_speech(formal_summary)
                    # Then ask the interactive question.
                    user_response = interactive_prompt(url)
                else:
                    text_to_speech("Session ended.")
            else:
                logging.info("Processing non-URL task.")
                response_text = ask_jarvis(decoded_text)
                text_to_speech(response_text)
                self.wfile.write(json.dumps({"response": response_text}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global stored_elements
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        logging.info("Received POST data: " + post_data.decode("utf-8"))
        if self.path.startswith("/scan-elements"):
            try:
                stored_elements = json.loads(post_data)
                logging.info("Elements successfully stored.")
            except json.JSONDecodeError as e:
                logging.error("Error decoding JSON: " + str(e))
                stored_elements = None
        self.send_response(200)
        self.end_headers()

def simulate_button_click(button_name, input_text=None):
    try:
        pyautogui.hotkey('ctrl', 'l')  # Focus on address bar
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'c')  # Copy URL
        time.sleep(0.5)
        url = subprocess.run("pbpaste", capture_output=True, text=True).stdout.strip()

        if input_text:
            input_text_escaped = input_text.replace('"', '\\"').replace("'", "\\'")
            script_type = (
                "var inputs = document.getElementsByTagName('input');"
                "for (var i = 0; i < inputs.length; i++) {"
                "if (inputs[i].type.toLowerCase() === 'text') {"
                "inputs[i].value = '" + input_text_escaped + "';"
                "break;"
                "}"
                "}"
            )
            command_type = (
                'osascript -e "tell application \\"Google Chrome\\" to execute front window\'s active tab javascript \\"'
                + script_type + '\\""'
            )
            subprocess.run(command_type, shell=True)
            time.sleep(1)
            logging.info(f"Typed '{input_text}' into the search box.")

        script_click = (
            "var buttons = document.getElementsByTagName('button');"
            "for (var i = 0; i < buttons.length; i++) {"
            "if (buttons[i].innerText.toLowerCase().includes('" + button_name.lower() + "')) {"
            "buttons[i].click();"
            "break;"
            "}"
            "}"
        )
        command_click = (
            'osascript -e "tell application \\"Google Chrome\\" to execute front window\'s active tab javascript \\"'
            + script_click + '\\""'
        )
        subprocess.run(command_click, shell=True)
        logging.info(f"Simulated clicking the '{button_name}' button.")
    except Exception as e:
        logging.error(f"Error simulating button click: {e}")

PORT = 8000

def start_server():
    with socketserver.TCPServer(("", PORT), JarvisHTTPRequestHandler) as httpd:
        logging.info(f"Serving on port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    logging.info("Jarvis assistant is running. Access the interface via browser.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down Jarvis.")

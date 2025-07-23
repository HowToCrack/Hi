# request modules for the py
# pip install speechrecognition pyttsx3 gTTS pygame flask requests langdetect
import os
import sys
import json
import time
import threading
import queue
import requests
import speech_recognition as sr
import pyttsx3
import subprocess
import webbrowser
import pyautogui
from flask import Flask, render_template, request, jsonify
from gtts import gTTS
from io import BytesIO
import pygame
import re
from langdetect import detect

# Initialize Flask app for WebView UI
app = Flask(__name__)

# Configuration
CONFIG = {
    "groq_api_key": "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",  # Replace with your actual Groq API key
    "model": "llama3-70b-8192",
    "api_url": "https://api.groq.com/openai/v1/chat/completions",
    "wake_word": "friday",  # Optional wake word
    "voice_enabled": True,
    "language": "en",  # Default language
    "log_file": "friday_logs.txt"
}

# Shared queue for communication between threads
command_queue = queue.Queue()
message_queue = queue.Queue()

# Initialize speech engine
try:
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)
    engine.setProperty('volume', 1.0)
except:
    engine = None

# Initialize pygame for audio playback
pygame.mixer.init()

class FridayAI:
    def __init__(self):
        self.last_command_time = time.time()
        self.is_listening = True
        self.current_language = "en"
        self.command_mode = False
        self.chat_history = []
        
    def detect_language(self, text):
        try:
            lang = detect(text)
            return "bn" if lang == "bn" else "en"
        except:
            return "en"
    
    def speak(self, text):
        if not CONFIG['voice_enabled']:
            return
            
        self.current_language = self.detect_language(text)
        
        # Add to chat history
        self.chat_history.append({
            'sender': 'Friday',
            'message': text,
            'timestamp': time.strftime("%H:%M:%S"),
            'language': self.current_language
        })
        message_queue.put({'type': 'chat_update', 'data': self.chat_history})
        
        if engine and self.current_language == "en":
            engine.say(text)
            engine.runAndWait()
        else:
            # Use gTTS for Bangla or if pyttsx3 fails
            try:
                tts = gTTS(text=text, lang=self.current_language)
                fp = BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                pygame.mixer.music.load(fp)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.clock.Clock().tick(10)
            except Exception as e:
                print(f"Speech synthesis error: {e}")
    
    def call_groq_api(self, prompt):
        headers = {
            "Authorization": f"Bearer {CONFIG['groq_api_key']}",
            "Content-Type": "application/json"
        }
        
        system_prompt = """
        You are Friday AI, created by Shipon. Only introduce yourself if asked. 
        Detect the user's language (Bangla/English) and reply in the same language. 
        Never mix Bangla and English in the same response.
        """
        
        payload = {
            "model": CONFIG["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        }
        
        try:
            response = requests.post(CONFIG["api_url"], headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"API Error: {e}")
            return "I'm having trouble connecting to the AI service. Please try again later."
    
    def execute_command(self, command_text):
        self.command_mode = True
        self.speak("Executing command")
        
        # Normalize command text
        command_text = command_text.lower().strip()
        self.current_language = self.detect_language(command_text)
        
        # Log the command
        self.log_interaction(f"Command: {command_text}")
        
        # Command patterns
        patterns = {
            'open_app': r'(open|start|run|launch)\s+(.*)',
            'create_file': r'(create|make)\s+(a\s+)?(file|document)\s+(named|called)?\s*(.*)',
            'delete_file': r'(delete|remove)\s+(file|document)\s+(named|called)?\s*(.*)',
            'shutdown': r'(shutdown|turn\s+off)\s+(the\s+)?computer',
            'restart': r'(restart|reboot)\s+(the\s+)?computer',
            'generate_code': r'(create|make|generate)\s+(a\s+)?(html|python|javascript|js)\s+(file|code|page)\s*(named|called)?\s*(.*)'
        }
        
        try:
            # Open application command
            if re.match(patterns['open_app'], command_text):
                match = re.search(patterns['open_app'], command_text)
                app_name = match.group(2)
                return self.open_application(app_name)
            
            # Create file command
            elif re.match(patterns['create_file'], command_text):
                match = re.search(patterns['create_file'], command_text)
                filename = match.group(4) or "untitled.txt"
                return self.create_file(filename)
            
            # Delete file command
            elif re.match(patterns['delete_file'], command_text):
                match = re.search(patterns['delete_file'], command_text)
                filename = match.group(4)
                return self.delete_file(filename)
            
            # Shutdown command
            elif re.match(patterns['shutdown'], command_text):
                return self.shutdown_computer()
            
            # Restart command
            elif re.match(patterns['restart'], command_text):
                return self.restart_computer()
            
            # Generate code command
            elif re.match(patterns['generate_code'], command_text):
                match = re.search(patterns['generate_code'], command_text)
                lang = match.group(3)
                filename = match.group(5) or f"untitled.{'html' if lang == 'html' else 'py' if lang == 'python' else 'js'}"
                return self.generate_code_file(lang, filename)
            
            # Default case - ask Groq API
            else:
                response = self.call_groq_api(command_text)
                self.speak(response)
                return response
            
        except Exception as e:
            error_msg = f"Sorry, I couldn't execute that command. Error: {str(e)}"
            self.speak(error_msg)
            return error_msg
        finally:
            self.command_mode = False
    
    def open_application(self, app_name):
        apps = {
            'chrome': 'chrome.exe',
            'browser': 'chrome.exe',
            'vscode': 'code',
            'visual studio code': 'code',
            'file explorer': 'explorer.exe',
            'notepad': 'notepad.exe',
            'calculator': 'calc.exe'
        }
        
        app_name_lower = app_name.lower()
        
        if app_name_lower in apps:
            try:
                if app_name_lower == 'file explorer':
                    subprocess.Popen(apps[app_name_lower])
                else:
                    os.startfile(apps[app_name_lower]) if sys.platform == 'win32' else subprocess.Popen(apps[app_name_lower])
                msg = f"Opening {app_name}"
                self.speak(msg)
                return msg
            except Exception as e:
                error_msg = f"Couldn't open {app_name}. Error: {str(e)}"
                self.speak(error_msg)
                return error_msg
        else:
            msg = f"I don't know how to open {app_name}"
            self.speak(msg)
            return msg
    
    def create_file(self, filename):
        try:
            if not filename:
                filename = "untitled.txt"
                
            if not '.' in filename:
                filename += ".txt"
                
            with open(filename, 'w') as f:
                f.write("")
                
            msg = f"Created file {filename}"
            self.speak(msg)
            return msg
        except Exception as e:
            error_msg = f"Couldn't create file. Error: {str(e)}"
            self.speak(error_msg)
            return error_msg
    
    def delete_file(self, filename):
        try:
            if not os.path.exists(filename):
                msg = f"File {filename} doesn't exist"
                self.speak(msg)
                return msg
                
            # Confirm deletion
            self.speak(f"Are you sure you want to delete {filename}? Say yes to confirm.")
            
            # Wait for confirmation
            confirm = self.listen_for_confirmation()
            
            if confirm and 'yes' in confirm.lower():
                os.remove(filename)
                msg = f"Deleted file {filename}"
                self.speak(msg)
                return msg
            else:
                msg = "File deletion cancelled"
                self.speak(msg)
                return msg
        except Exception as e:
            error_msg = f"Couldn't delete file. Error: {str(e)}"
            self.speak(error_msg)
            return error_msg
    
    def shutdown_computer(self):
        try:
            self.speak("Are you sure you want to shutdown the computer? Say yes to confirm.")
            confirm = self.listen_for_confirmation()
            
            if confirm and 'yes' in confirm.lower():
                self.speak("Shutting down the computer in 5 seconds")
                time.sleep(5)
                if sys.platform == 'win32':
                    os.system("shutdown /s /t 1")
                else:
                    os.system("shutdown -h now")
                return "Shutting down"
            else:
                msg = "Shutdown cancelled"
                self.speak(msg)
                return msg
        except Exception as e:
            error_msg = f"Couldn't shutdown. Error: {str(e)}"
            self.speak(error_msg)
            return error_msg
    
    def restart_computer(self):
        try:
            self.speak("Are you sure you want to restart the computer? Say yes to confirm.")
            confirm = self.listen_for_confirmation()
            
            if confirm and 'yes' in confirm.lower():
                self.speak("Restarting the computer in 5 seconds")
                time.sleep(5)
                if sys.platform == 'win32':
                    os.system("shutdown /r /t 1")
                else:
                    os.system("shutdown -r now")
                return "Restarting"
            else:
                msg = "Restart cancelled"
                self.speak(msg)
                return msg
        except Exception as e:
            error_msg = f"Couldn't restart. Error: {str(e)}"
            self.speak(error_msg)
            return error_msg
    
    def generate_code_file(self, lang, filename):
        try:
            if not filename:
                if lang == 'html':
                    filename = 'index.html'
                elif lang == 'python':
                    filename = 'script.py'
                elif lang == 'javascript' or lang == 'js':
                    filename = 'app.js'
            
            if lang == 'html':
                content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #f0f0f0;
        }
        .container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello World</h1>
        <p>This is your new HTML file.</p>
    </div>
</body>
</html>"""
            elif lang == 'python':
                content = """# Python script generated by Friday AI

def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()"""
            elif lang == 'javascript' or lang == 'js':
                content = """// JavaScript file generated by Friday AI

console.log('Hello, World!');

function greet(name) {
    return `Hello, ${name}!`;
}

// Example usage
console.log(greet('Friday'));"""
            
            with open(filename, 'w') as f:
                f.write(content)
            
            # Open in VS Code if available
            try:
                subprocess.Popen(['code', filename])
            except:
                pass
            
            msg = f"Created {lang} file {filename}"
            self.speak(msg)
            return msg
        except Exception as e:
            error_msg = f"Couldn't generate code file. Error: {str(e)}"
            self.speak(error_msg)
            return error_msg
    
    def listen_for_confirmation(self, timeout=5):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source)
            try:
                print("Listening for confirmation...")
                audio = recognizer.listen(source, timeout=timeout)
                text = recognizer.recognize_google(audio)
                return text
            except sr.WaitTimeoutError:
                return None
            except Exception as e:
                print(f"Confirmation error: {e}")
                return None
    
    def log_interaction(self, text):
        with open(CONFIG['log_file'], 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {text}\n")

# Initialize Friday AI
friday = FridayAI()

def voice_listener():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        
        while True:
            if not CONFIG['voice_enabled']:
                time.sleep(1)
                continue
                
            try:
                print("Listening...")
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=5)
                text = recognizer.recognize_google(audio)
                print(f"Recognized: {text}")
                
                # Add to chat history
                friday.chat_history.append({
                    'sender': 'User',
                    'message': text,
                    'timestamp': time.strftime("%H:%M:%S"),
                    'language': friday.detect_language(text)
                })
                message_queue.put({'type': 'chat_update', 'data': friday.chat_history})
                
                # Check for wake word if configured
                if CONFIG['wake_word'] and CONFIG['wake_word'].lower() in text.lower():
                    command_text = text.lower().replace(CONFIG['wake_word'].lower(), '').strip()
                    command_queue.put(command_text)
                elif not CONFIG['wake_word']:
                    command_queue.put(text)
                    
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                print("Could not understand audio")
                continue
            except Exception as e:
                print(f"Error in voice listener: {e}")
                time.sleep(1)

def process_commands():
    while True:
        command = command_queue.get()
        if command:
            print(f"Processing command: {command}")
            response = friday.execute_command(command)
            print(f"Response: {response}")

# Flask routes for WebView UI
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    text = data.get('message', '').strip()
    
    if text:
        # Add to chat history
        friday.chat_history.append({
            'sender': 'User',
            'message': text,
            'timestamp': time.strftime("%H:%M:%S"),
            'language': friday.detect_language(text)
        })
        message_queue.put({'type': 'chat_update', 'data': friday.chat_history})
        
        # Process the message
        command_queue.put(text)
        
    return jsonify({'status': 'success'})

@app.route('/get_updates')
def get_updates():
    try:
        message = message_queue.get(timeout=10)
        return jsonify(message)
    except queue.Empty:
        return jsonify({'type': 'no_update'})

@app.route('/toggle_voice', methods=['POST'])
def toggle_voice():
    CONFIG['voice_enabled'] = not CONFIG['voice_enabled']
    return jsonify({'status': 'success', 'voice_enabled': CONFIG['voice_enabled']})

# HTML Template
@app.route('/template')
def template():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Friday AI Assistant</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Roboto', sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            color: #fff;
            height: 100vh;
            overflow: hidden;
            position: relative;
        }
        
        #particles-js {
            position: absolute;
            width: 100%;
            height: 100%;
            z-index: 0;
        }
        
        .container {
            position: relative;
            z-index: 1;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            margin-bottom: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        h1 {
            font-weight: 500;
            font-size: 24px;
        }
        
        .voice-toggle {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 34px;
        }
        
        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 34px;
        }
        
        .slider:before {
            position: absolute;
            content: "";
            height: 26px;
            width: 26px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        
        input:checked + .slider {
            background-color: #4CAF50;
        }
        
        input:checked + .slider:before {
            transform: translateX(26px);
        }
        
        .voice-icon {
            font-size: 20px;
        }
        
        .center-circle {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.1);
            border: 2px solid rgba(255, 255, 255, 0.2);
            margin: 20px auto;
            display: flex;
            justify-content: center;
            align-items: center;
            position: relative;
            transition: all 0.3s ease;
        }
        
        .center-circle.active {
            background: rgba(76, 175, 80, 0.2);
            border-color: #4CAF50;
            box-shadow: 0 0 20px rgba(76, 175, 80, 0.5);
        }
        
        .center-circle::after {
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 50%;
            border: 5px solid transparent;
            border-top-color: #4CAF50;
            animation: spin 1.5s linear infinite;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .center-circle.listening::after {
            opacity: 0.7;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .mic-icon {
            font-size: 40px;
            color: rgba(255, 255, 255, 0.7);
        }
        
        .center-circle.active .mic-icon {
            color: #4CAF50;
        }
        
        .chat-container {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 20px;
            padding-right: 10px;
        }
        
        .chat-message {
            display: flex;
            margin-bottom: 15px;
        }
        
        .chat-message.user {
            justify-content: flex-end;
        }
        
        .chat-message.assistant {
            justify-content: flex-start;
        }
        
        .message-bubble {
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            position: relative;
            word-wrap: break-word;
        }
        
        .user .message-bubble {
            background: #4CAF50;
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .assistant .message-bubble {
            background: rgba(255, 255, 255, 0.1);
            border-bottom-left-radius: 4px;
        }
        
        .message-time {
            font-size: 11px;
            color: rgba(255, 255, 255, 0.6);
            margin-top: 4px;
            text-align: right;
        }
        
        .input-container {
            display: flex;
            gap: 10px;
            padding: 10px 0;
        }
        
        input[type="text"] {
            flex: 1;
            padding: 12px 15px;
            border: none;
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.1);
            color: white;
            font-size: 16px;
            outline: none;
        }
        
        input[type="text"]::placeholder {
            color: rgba(255, 255, 255, 0.5);
        }
        
        button {
            padding: 12px 20px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 24px;
            cursor: pointer;
            font-size: 16px;
            transition: background 0.3s;
        }
        
        button:hover {
            background: #45a049;
        }
        
        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 6px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.1);
        }
        
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.2);
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.3);
        }
        
        .language-indicator {
            font-size: 12px;
            color: rgba(255, 255, 255, 0.6);
            margin-top: 2px;
        }
    </style>
</head>
<body>
    <div id="particles-js"></div>
    <div class="container">
        <header>
            <h1>Friday AI Assistant</h1>
            <div class="voice-toggle">
                <span class="voice-icon">🔊</span>
                <label class="switch">
                    <input type="checkbox" id="voiceToggle" checked>
                    <span class="slider"></span>
                </label>
            </div>
        </header>
        
        <div class="center-circle" id="centerCircle">
            <div class="mic-icon">🎤</div>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <!-- Chat messages will appear here -->
        </div>
        
        <div class="input-container">
            <input type="text" id="messageInput" placeholder="Type your message here...">
            <button id="sendButton">Send</button>
        </div>
    </div>
    
    <script>
        // Initialize particles.js
        particlesJS("particles-js", {
            "particles": {
                "number": {
                    "value": 80,
                    "density": {
                        "enable": true,
                        "value_area": 800
                    }
                },
                "color": {
                    "value": "#ffffff"
                },
                "shape": {
                    "type": "circle",
                    "stroke": {
                        "width": 0,
                        "color": "#000000"
                    },
                    "polygon": {
                        "nb_sides": 5
                    }
                },
                "opacity": {
                    "value": 0.3,
                    "random": false,
                    "anim": {
                        "enable": false,
                        "speed": 1,
                        "opacity_min": 0.1,
                        "sync": false
                    }
                },
                "size": {
                    "value": 3,
                    "random": true,
                    "anim": {
                        "enable": false,
                        "speed": 40,
                        "size_min": 0.1,
                        "sync": false
                    }
                },
                "line_linked": {
                    "enable": true,
                    "distance": 150,
                    "color": "#ffffff",
                    "opacity": 0.2,
                    "width": 1
                },
                "move": {
                    "enable": true,
                    "speed": 2,
                    "direction": "none",
                    "random": false,
                    "straight": false,
                    "out_mode": "out",
                    "bounce": false,
                    "attract": {
                        "enable": false,
                        "rotateX": 600,
                        "rotateY": 1200
                    }
                }
            },
            "interactivity": {
                "detect_on": "canvas",
                "events": {
                    "onhover": {
                        "enable": true,
                        "mode": "grab"
                    },
                    "onclick": {
                        "enable": true,
                        "mode": "push"
                    },
                    "resize": true
                },
                "modes": {
                    "grab": {
                        "distance": 140,
                        "line_linked": {
                            "opacity": 1
                        }
                    },
                    "bubble": {
                        "distance": 400,
                        "size": 40,
                        "duration": 2,
                        "opacity": 8,
                        "speed": 3
                    },
                    "repulse": {
                        "distance": 200,
                        "duration": 0.4
                    },
                    "push": {
                        "particles_nb": 4
                    },
                    "remove": {
                        "particles_nb": 2
                    }
                }
            },
            "retina_detect": true
        });
        
        // DOM elements
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const chatContainer = document.getElementById('chatContainer');
        const voiceToggle = document.getElementById('voiceToggle');
        const centerCircle = document.getElementById('centerCircle');
        
        // Check voice status on load
        checkVoiceStatus();
        
        // Event listeners
        sendButton.addEventListener('click', sendMessage);
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        voiceToggle.addEventListener('change', toggleVoice);
        
        // Long-polling for updates
        function getUpdates() {
            fetch('/get_updates')
                .then(response => response.json())
                .then(data => {
                    if (data.type === 'chat_update') {
                        updateChat(data.data);
                    }
                    
                    // Check if voice is listening
                    if (data.type === 'listening_status') {
                        centerCircle.classList.toggle('listening', data.listening);
                    }
                    
                    getUpdates(); // Continue polling
                })
                .catch(error => {
                    console.error('Error fetching updates:', error);
                    setTimeout(getUpdates, 1000); // Retry after 1 second
                });
        }
        
        // Start polling for updates
        getUpdates();
        
        // Functions
        function sendMessage() {
            const message = messageInput.value.trim();
            if (message) {
                addMessageToChat('user', message, new Date(), 'en');
                messageInput.value = '';
                
                fetch('/send_message', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message })
                })
                .catch(error => console.error('Error sending message:', error));
            }
        }
        
        function toggleVoice() {
            const enabled = voiceToggle.checked;
            
            fetch('/toggle_voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.voice_enabled) {
                    centerCircle.classList.add('active');
                } else {
                    centerCircle.classList.remove('active');
                }
            })
            .catch(error => console.error('Error toggling voice:', error));
        }
        
        function checkVoiceStatus() {
            fetch('/toggle_voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                voiceToggle.checked = data.voice_enabled;
                if (data.voice_enabled) {
                    centerCircle.classList.add('active');
                } else {
                    centerCircle.classList.remove('active');
                }
            })
            .catch(error => console.error('Error checking voice status:', error));
        }
        
        function updateChat(messages) {
            chatContainer.innerHTML = '';
            
            messages.forEach(msg => {
                addMessageToChat(msg.sender, msg.message, msg.timestamp, msg.language);
            });
            
            // Scroll to bottom
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function addMessageToChat(sender, message, timestamp, language) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${sender.toLowerCase()}`;
            
            const bubbleDiv = document.createElement('div');
            bubbleDiv.className = 'message-bubble';
            bubbleDiv.textContent = message;
            
            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-time';
            
            if (typeof timestamp === 'string') {
                timeDiv.textContent = timestamp;
            } else {
                timeDiv.textContent = timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            }
            
            const langDiv = document.createElement('div');
            langDiv.className = 'language-indicator';
            langDiv.textContent = language === 'bn' ? 'Bangla' : 'English';
            
            bubbleDiv.appendChild(timeDiv);
            bubbleDiv.appendChild(langDiv);
            messageDiv.appendChild(bubbleDiv);
            chatContainer.appendChild(messageDiv);
            
            // Scroll to bottom
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        // Visual feedback for voice listening
        centerCircle.addEventListener('click', function() {
            if (voiceToggle.checked) {
                this.classList.toggle('listening');
                
                // Send a mock listening status (in a real app, this would come from the server)
                setTimeout(() => {
                    this.classList.toggle('listening');
                }, 3000);
            }
        });
    </script>
</body>
</html>
"""

def main():
    # Start voice listener thread
    voice_thread = threading.Thread(target=voice_listener, daemon=True)
    voice_thread.start()
    
    # Start command processor thread
    command_thread = threading.Thread(target=process_commands, daemon=True)
    command_thread.start()
    
    # Start Flask web server
    webbrowser.open('http://localhost:5000')
    app.run(debug=False)

if __name__ == "__main__":
    # Initial greeting
    friday.speak("Friday AI Assistant initialized. How can I help you?")
    main()
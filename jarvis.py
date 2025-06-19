import os
import json
import time
import webbrowser
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Dict

import numpy as np
import pyautogui
import pyttsx3
import pytesseract
import sounddevice as sd
from PIL import Image
from scipy.io.wavfile import write
from bs4 import BeautifulSoup
import requests
import speech_recognition as sr
from openai import OpenAI

OPENAI_API_KEY = ""


client = OpenAI(api_key=OPENAI_API_KEY)

MAX_HISTORY = 20
chat_history: List[Dict[str, str]] = [
    {"role": "system", "content": "You are Jarvis, a witty yet concise AI assistant living on the user's laptop."}
]

INDEX_PATH = Path("file_index.json")
SEARCH_ROOT = "C:/"  


FS = 44_100 
SILENCE_THRESHOLD = 1000 
SILENCE_DURATION = 1.0 
CHUNK_SECS = 0.5

def index_files(base: str = SEARCH_ROOT, limit: int = 10_000):
    print("[Jarvis] Building file index …")
    files = {}
    for root, _dirs, file_names in os.walk(base):
        for fname in file_names:
            files[fname.lower()] = os.path.join(root, fname)
            if len(files) >= limit:
                break
        if len(files) >= limit:
            break
    with INDEX_PATH.open("w", encoding="utf‑8") as f:
        json.dump(files, f)
    print(f"[Jarvis] Indexed {len(files):,} files.")


def load_index() -> Dict[str, str]:
    if not INDEX_PATH.exists():
        index_files()
    return json.loads(INDEX_PATH.read_text())


def record_until_silence() -> Path:
    print("Listening, speak now)")
    audio_chunks = []
    silence_start = None

    while True:
        chunk = sd.rec(int(CHUNK_SECS * FS), samplerate=FS, channels=1, dtype="int16")
        sd.wait()
        audio_chunks.append(chunk)
        if np.max(np.abs(chunk)) < SILENCE_THRESHOLD:
            silence_start = silence_start or time.time()
            if time.time() - silence_start >= SILENCE_DURATION:
                break
        else:
            silence_start = None

    audio = np.concatenate(audio_chunks)
    wav_path = Path("voice_input.wav")
    write(wav_path, FS, audio)
    return wav_path


def transcribe(path: Path) -> str:
    recognizer = sr.Recognizer()
    with sr.AudioFile(str(path)) as source:
        audio = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio)
        print(f"{text}")
        return text.lower()
    except sr.UnknownValueError:
        return ""


def speak(text: str):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


def chatgpt(prompt: str) -> str:
    global chat_history
    chat_history.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(model="gpt-4o", messages=chat_history[-MAX_HISTORY:])
    reply = response.choices[0].message.content.strip()
    chat_history.append({"role": "assistant", "content": reply})
    return reply

def google_search(query: str) -> str:
    try:
        url = f"https://www.google.com/search?q={query}"
        soup = BeautifulSoup(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text, "html.parser")
        result = soup.find(class_="g").find("a")["href"]
        return result
    except Exception as err:
        print("[Jarvis] Search error:", err)
        return url


def open_file(keyword: str):
    files = load_index()
    for name, path in files.items():
        if keyword in name:
            os.startfile(path)
            speak(f"Opening {name}")
            return
    speak("I couldn't find that file.")


def send_email():
    from_email = input("From (gmail): ")
    password = input("App‑password: ")
    to_email = input("To: ")
    subject = input("Subject: ")
    body = input("Body: ")

    msg = MIMEMultipart(); msg["From"]=from_email; msg["To"]=to_email; msg["Subject"]=subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(); server.login(from_email, password); server.send_message(msg)
        speak("Email sent successfully!")
    except Exception as err:
        speak(f"Failed to send email: {err}")


def code_helper(prompt: str):
    img_path = Path("screenshot.png")
    pyautogui.screenshot(str(img_path))
    extracted_text = pytesseract.image_to_string(Image.open(img_path))
    reply = chatgpt(f"User prompt: {prompt}\n\nCode on screen:\n{extracted_text[:4000]}")
    print("\nCode Analysis:\n", reply)
    speak("I've provided feedback on your code.")


def parse_and_execute(cmd: str):
    if not cmd:
        return
    if any(w in cmd for w in ["open", "launch"]):
        keyword = cmd.replace("open", "").replace("launch", "").strip()
        open_file(keyword)
    elif cmd.startswith(("search", "find")):
        query = cmd.replace("search", "").replace("find", "").strip()
        link = google_search(query)
        webbrowser.open(link)
    elif "send email" in cmd:
        send_email()
    elif "help me with this code" in cmd:
        prompt = chatgpt("What specifically do you need help with?")
        code_helper(prompt)
    else:
        reply = chatgpt(cmd)
        print("Jarvis:", reply)
        speak(reply)


def listen_for_wake_word():
    while True:
        audio = record_until_silence()
        text = transcribe(audio)
        if any(w in text for w in ["hey jarvis", "jarvis"]):
            speak("Yes?")
            return


def main():
    index_files() 
    while True:
        try:
            listen_for_wake_word()
            cmd_audio = record_until_silence()
            command = transcribe(cmd_audio)
            parse_and_execute(command)
        except KeyboardInterrupt:
            print("Exiting …")
            break
        except Exception as err:
            print("[Jarvis] Error:", err)
            speak("I hit an error but I'm still listening.")


if __name__ == "__main__":
    main()

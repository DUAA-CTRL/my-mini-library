import os
import re
import random
from datetime import datetime
from io import BytesIO

import requests
from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_file,
)

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId
from gridfs import GridFS


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv(override=True)

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "my-library-secret"
)

MONGO_URI = os.getenv(
    "MONGO_URI",
    ""
).strip()

MONGO_DB = os.getenv(
    "MONGO_DB",
    "my_library"
).strip()

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434"
).strip()

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:latest"
).strip()

OLLAMA_API_KEY = os.getenv(
    "OLLAMA_API_KEY",
    ""
).strip()

MAX_UPLOAD_MB = int(
    os.getenv(
        "MAX_UPLOAD_MB",
        "50"
    )
)

app.config["MAX_CONTENT_LENGTH"] = (
    MAX_UPLOAD_MB * 1024 * 1024
)


# =========================================================
# APP NAME
# =========================================================

APP_NAME = "My Mini Library"
CHATBOT_NAME = "Lumi"


# =========================================================
# QUOTES
# =========================================================

QUOTES = [
    "A room without books is like a body without a soul. — Cicero",
    "Today a reader, tomorrow a leader. — Margaret Fuller",
    "There is no friend as loyal as a book. — Ernest Hemingway",
    "A book is a dream that you hold in your hand. — Neil Gaiman",
    "Reading is to the mind what exercise is to the body. — Joseph Addison",
    "Books are a uniquely portable magic. — Stephen King",
    "The more that you read, the more things you will know. — Dr. Seuss",
    "Reading brings us unknown friends. — Honoré de Balzac",
    "A good book is an event in my life. — Stendhal",
    "Books open your mind, broaden your horizons, and strengthen your heart.",
    "Every book is a journey waiting to begin.",
    "Small reading habits create big changes.",
    "Read a little today. Learn a little more tomorrow.",
    "Your next favourite book may already be waiting for you.",
]


# =========================================================
# MONGODB
# =========================================================

if not MONGO_URI:

    print("WARNING: MONGO_URI is missing.")

    client = None
    db = None
    books = None
    fs = None
    MONGO_OK = False

else:

    try:

        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
        )

        client.admin.command("ping")

        db = client[MONGO_DB]
        books = db["books"]
        fs = GridFS(db)

        MONGO_OK = True

        print("MongoDB connection: CONNECTED")

    except Exception as e:

        print(
            "MongoDB connection error:",
            e
        )

        client = None
        db = None
        books = None
        fs = None
        MONGO_OK = False


# =========================================================
# CONSTANTS
# =========================================================

GENRES = [
    "Fan Fiction",
    "Psychology",
    "Philosophy",
    "Self Help",
    "CS",
    "English",
    "Other",
]

STICKERS = [
    "🌙",
    "🖤",
    "✨",
    "🎀",
    "📚",
    "🌷",
    "⭐",
    "☁️",
]


# =========================================================
# HELPERS
# =========================================================

def clean(value):
    return (value or "").strip()


def valid_object_id(value):

    try:
        return ObjectId(value)

    except Exception:
        return None


def serialize(book):

    return {
        "id": str(book["_id"]),

        "title": book.get(
            "title",
            ""
        ),

        "genre": book.get(
            "genre",
            "Other"
        ),

        "status": book.get(
            "status",
            "reading"
        ),

        "sticker": book.get(
            "sticker",
            "🌙"
        ),

        "file_id": (
            str(book["file_id"])
            if book.get("file_id")
            else None
        ),

        "filename": book.get(
            "filename",
            ""
        ),
    }


def get_random_quote():
    return random.choice(QUOTES)


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    q = clean(
        request.args.get("q")
    )

    genre = clean(
        request.args.get("genre")
    )

    query = {}

    if q:

        regex = {
            "$regex": re.escape(q),
            "$options": "i",
        }

        query["$or"] = [
            {
                "title": regex
            },
            {
                "genre": regex
            },
        ]

    if genre and genre != "All":

        query["genre"] = genre

    docs = []

    if MONGO_OK:

        try:

            docs = [
                serialize(book)
                for book in books.find(query)
                .sort("_id", -1)
            ]

        except PyMongoError as e:

            print(
                "MongoDB read error:",
                e
            )

            docs = []

    return render_template(

        "index.html",

        books=docs,

        genres=GENRES,

        stickers=STICKERS,

        q=q,

        active_genre=(
            genre or "All"
        ),

        app_name=APP_NAME,

        chatbot_name=CHATBOT_NAME,

        quote=get_random_quote(),

    )


# =========================================================
# ADD BOOK / PDF
# =========================================================

@app.post("/add")
def add_book():

    if not MONGO_OK:

        return (
            "MongoDB is not connected.",
            500
        )

    title = clean(
        request.form.get("title")
    )

    genre = clean(
        request.form.get("genre")
    ) or "Other"

    status = clean(
        request.form.get("status")
    ) or "reading"

    sticker = clean(
        request.form.get("sticker")
    ) or "🌙"

    uploaded = request.files.get(
        "pdf"
    )

    if not title:

        return redirect(
            url_for("index")
        )

    file_id = None
    filename = ""

    try:

        if uploaded and uploaded.filename:

            filename = uploaded.filename

            data = uploaded.read()

            file_id = fs.put(

                data,

                filename=filename,

                content_type=(
                    uploaded.mimetype
                    or "application/pdf"
                ),

            )

        books.insert_one({

            "title": title,

            "genre": genre,

            "status": status,

            "sticker": sticker,

            "file_id": file_id,

            "filename": filename,

            "created_at": datetime.utcnow(),

        })

    except Exception as e:

        print(
            "Add book error:",
            e
        )

        return (
            "Could not add book.",
            500
        )

    return redirect(
        url_for("index")
    )


# =========================================================
# EDIT BOOK
# =========================================================

@app.post("/edit/<id>")
def edit_book(id):

    if not MONGO_OK:

        return (
            "MongoDB is not connected.",
            500
        )

    object_id = valid_object_id(id)

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    update = {

        "title": clean(
            request.form.get("title")
        ),

        "genre": clean(
            request.form.get("genre")
        ) or "Other",

        "status": clean(
            request.form.get("status")
        ) or "reading",

        "sticker": clean(
            request.form.get("sticker")
        ) or "🌙",

    }

    try:

        old = books.find_one({
            "_id": object_id
        })

        if not old:

            return (
                "Book not found.",
                404
            )

        uploaded = request.files.get(
            "pdf"
        )

        if uploaded and uploaded.filename:

            if old.get("file_id"):

                try:

                    fs.delete(
                        old["file_id"]
                    )

                except Exception:
                    pass

            data = uploaded.read()

            update["file_id"] = fs.put(

                data,

                filename=uploaded.filename,

                content_type=(
                    uploaded.mimetype
                    or "application/pdf"
                ),

            )

            update["filename"] = (
                uploaded.filename
            )

        books.update_one(

            {
                "_id": object_id
            },

            {
                "$set": update
            }

        )

    except Exception as e:

        print(
            "Edit book error:",
            e
        )

        return (
            "Could not edit book.",
            500
        )

    return redirect(
        url_for("index")
    )


# =========================================================
# DELETE BOOK
# =========================================================

@app.post("/delete/<id>")
def delete_book(id):

    if not MONGO_OK:

        return (
            "MongoDB is not connected.",
            500
        )

    object_id = valid_object_id(id)

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    try:

        book = books.find_one({
            "_id": object_id
        })

        if book and book.get("file_id"):

            try:

                fs.delete(
                    book["file_id"]
                )

            except Exception:
                pass

        books.delete_one({
            "_id": object_id
        })

    except Exception as e:

        print(
            "Delete book error:",
            e
        )

        return (
            "Could not delete book.",
            500
        )

    return redirect(
        url_for("index")
    )


# =========================================================
# PDF READER PAGE
# =========================================================

@app.get("/read/<id>")
def read_pdf(id):

    if not MONGO_OK:

        return (
            "MongoDB is not connected.",
            500
        )

    object_id = valid_object_id(id)

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    try:

        book = books.find_one({
            "_id": object_id
        })

        if not book:

            return (
                "Book not found.",
                404
            )

        if not book.get("file_id"):

            return (
                "PDF not found.",
                404
            )

        return render_template(

            "pdf.html",

            book=serialize(book),

        )

    except Exception as e:

        print(
            "PDF reader error:",
            e
        )

        return (
            "Could not open PDF reader.",
            500
        )


# =========================================================
# GET PDF FROM GRIDFS
# =========================================================

def _get_pdf_file(id):

    if not MONGO_OK:

        return (
            None,
            None,
            (
                "MongoDB is not connected.",
                500
            )
        )

    object_id = valid_object_id(id)

    if not object_id:

        return (
            None,
            None,
            (
                "Invalid book ID.",
                400
            )
        )

    try:

        book = books.find_one({
            "_id": object_id
        })

        if not book:

            return (
                None,
                None,
                (
                    "Book not found.",
                    404
                )
            )

        if not book.get("file_id"):

            return (
                None,
                None,
                (
                    "PDF not found.",
                    404
                )
            )

        file_data = fs.get(
            book["file_id"]
        )

        return (
            book,
            file_data,
            None
        )

    except Exception as e:

        print(
            "PDF error:",
            e
        )

        return (
            None,
            None,
            (
                "Could not read PDF.",
                500
            )
        )


# =========================================================
# VIEW PDF
# =========================================================

@app.get("/pdf/<id>")
def pdf(id):

    book, file_data, error = (
        _get_pdf_file(id)
    )

    if error:
        return error

    filename = (
        book.get("filename")
        or "library.pdf"
    ).replace(
        '"',
        ""
    )

    response = send_file(

        BytesIO(
            file_data.read()
        ),

        mimetype=(
            file_data.content_type
            or "application/pdf"
        ),

        download_name=filename,

        as_attachment=False,

        conditional=True,

        max_age=0,

    )

    response.headers[
        "Content-Disposition"
    ] = (
        f'inline; filename="{filename}"'
    )

    response.headers[
        "Cache-Control"
    ] = (
        "private, no-cache, "
        "no-store, must-revalidate"
    )

    response.headers[
        "Accept-Ranges"
    ] = "bytes"

    return response


# =========================================================
# DOWNLOAD PDF
# =========================================================

@app.get("/download/<id>")
def download_pdf(id):

    book, file_data, error = (
        _get_pdf_file(id)
    )

    if error:
        return error

    return send_file(

        BytesIO(
            file_data.read()
        ),

        mimetype=(
            file_data.content_type
            or "application/pdf"
        ),

        download_name=(
            book.get("filename")
            or "library.pdf"
        ),

        as_attachment=True,

        conditional=True,

    )

# =========================================================
# PDF HIGHLIGHTS
# =========================================================

@app.get("/api/highlights/<id>")
def get_highlights(id):

    if not MONGO_OK:
        return jsonify({
            "error": "MongoDB is not connected."
        }), 500

    object_id = valid_object_id(id)

    if not object_id:
        return jsonify({
            "error": "Invalid book ID."
        }), 400

    try:

        book = books.find_one({
            "_id": object_id
        })

        if not book:
            return jsonify({
                "error": "Book not found."
            }), 404

        highlights = book.get(
            "highlights",
            []
        )

        return jsonify({
            "highlights": highlights
        })

    except Exception as e:

        print(
            "Get highlights error:",
            e
        )

        return jsonify({
            "error": "Could not load highlights."
        }), 500


@app.post("/api/highlights/<id>")
def save_highlight(id):

    if not MONGO_OK:
        return jsonify({
            "error": "MongoDB is not connected."
        }), 500

    object_id = valid_object_id(id)

    if not object_id:
        return jsonify({
            "error": "Invalid book ID."
        }), 400

    try:

        book = books.find_one({
            "_id": object_id
        })

        if not book:
            return jsonify({
                "error": "Book not found."
            }), 404

        data = request.get_json(
            silent=True
        ) or {}

        highlight = {

            "id": clean(
                data.get("id")
            ),

            "page": int(
                data.get("page", 1)
            ),

            "text": clean(
                data.get("text")
            ),

            "top": float(
                data.get("top", 0)
            ),

            "left": float(
                data.get("left", 0)
            ),

            "width": float(
                data.get("width", 0)
            ),

            "height": float(
                data.get("height", 0)
            ),

            "created_at":
                datetime.utcnow().isoformat(),

        }

        if not highlight["id"]:
            return jsonify({
                "error": "Highlight ID is required."
            }), 400

        if not highlight["text"]:
            return jsonify({
                "error": "Highlight text is required."
            }), 400

        books.update_one(

            {
                "_id": object_id
            },

            {
                "$pull": {
                    "highlights": {
                        "id": highlight["id"]
                    }
                }
            }

        )

        books.update_one(

            {
                "_id": object_id
            },

            {
                "$push": {
                    "highlights": highlight
                }
            }

        )

        return jsonify({
            "success": True,
            "highlight": highlight
        })

    except Exception as e:

        print(
            "Save highlight error:",
            e
        )

        return jsonify({
            "error": "Could not save highlight."
        }), 500


@app.delete("/api/highlights/<id>/<highlight_id>")
def delete_highlight(
    id,
    highlight_id
):

    if not MONGO_OK:
        return jsonify({
            "error": "MongoDB is not connected."
        }), 500

    object_id = valid_object_id(id)

    if not object_id:
        return jsonify({
            "error": "Invalid book ID."
        }), 400

    try:

        result = books.update_one(

            {
                "_id": object_id
            },

            {
                "$pull": {
                    "highlights": {
                        "id": highlight_id
                    }
                }
            }

        )

        return jsonify({
            "success": True,
            "deleted":
                result.modified_count > 0
        })

    except Exception as e:

        print(
            "Delete highlight error:",
            e
        )

        return jsonify({
            "error": "Could not delete highlight."
        }), 500

# =========================================================
# OLLAMA
# =========================================================

def ask_ollama(prompt):

    try:

        headers = {
            "Content-Type":
                "application/json"
        }

        if OLLAMA_API_KEY:

            headers["Authorization"] = (
                f"Bearer {OLLAMA_API_KEY}"
            )

        response = requests.post(

            f"{OLLAMA_URL.rstrip('/')}"
            "/api/generate",

            headers=headers,

            json={

                "model": OLLAMA_MODEL,

                "prompt": prompt,

                "stream": False,

                "options": {

                    "temperature": 0.2,

                    "num_predict": 180,

                },

                "keep_alive": "10m",

            },

            timeout=120,

        )

        response.raise_for_status()

        data = response.json()

        answer = clean(
            data.get("response")
        )

        if answer:
            return answer

        return None

    except Exception as e:

        print(
            "Ollama error:",
            e
        )

        return None


# =========================================================
# QUICK WORD MEANINGS
# =========================================================

QUICK_MEANINGS = {

    "system":
        "A set of connected parts, rules, or processes "
        "that work together for a particular purpose.",

    "entropy":
        "A measure of disorder or randomness in a system. "
        "In simple words, higher entropy means things are "
        "less organized or more spread out.",

    "disorder":
        "A lack of order or organization. "
        "Example: A messy room is in disorder.",

    "lack":
        "A situation in which something is missing or "
        "not available. Example: There is a lack of time.",

    "hard":
        "Difficult to do, understand, or deal with. "
        "Example: This is a hard question.",

    "easy":
        "Not difficult; something that can be done "
        "without much effort.",

    "meaning":
        "The idea, definition, or significance of something.",

    "library":
        "A place or system where books and other information "
        "are collected, organized, and made available.",

    "computer":
        "An electronic machine that processes, stores, "
        "and works with information.",

    "technology":
        "The practical use of scientific knowledge to create "
        "tools, machines, or systems.",

    "information":
        "Facts or knowledge about something or someone.",

    "philosophy":
        "The study of fundamental questions about life, "
        "knowledge, reality, truth, and existence.",

    "psychology":
        "The scientific study of the mind and behavior.",

    "empathy":
        "The ability to understand or share another "
        "person's feelings.",

    "anxiety":
        "A feeling of worry, nervousness, or unease.",

    "motivation":
        "The reason or drive that makes someone want "
        "to do something.",

    "discipline":
        "The ability to control your actions and keep "
        "following a plan or set of rules.",

    "knowledge":
        "Information and understanding gained through "
        "learning or experience.",

    "wisdom":
        "The ability to use knowledge and experience "
        "to make good decisions.",

    "curiosity":
        "A strong desire to learn, know, or discover "
        "something.",

    "procrastination":
        "The habit of delaying something that should "
        "be done.",

    "confidence":
        "Belief in your own abilities or judgment.",

    "resilience":
        "The ability to recover and continue after "
        "difficulties or setbacks.",

    "beautiful":
        "Pleasing to the senses or to the mind; "
        "attractive or lovely.",

    "important":
        "Having great value, meaning, or significance.",

    "success":
        "The achievement of a desired goal or result.",

    "failure":
        "The lack of success in achieving a desired goal.",

    "love":
        "A strong feeling of affection, care, or deep "
        "emotional attachment.",

    "fear":
        "An unpleasant feeling caused by the belief "
        "that something dangerous may happen.",

    "hope":
        "A feeling of expectation and desire for "
        "something good to happen.",

    "dream":
        "A series of thoughts or images during sleep, "
        "or a strongly desired goal or ambition.",

    "meticulous":
        "Very careful and precise, especially about "
        "small details. Example: She is meticulous "
        "about her work.",

}


# =========================================================
# LUMI — MEANING API
# =========================================================
# IMPORTANT:
# Your index.html calls:
# POST /api/meaning
# with:
# word=...
#
# This route was missing before.
# =========================================================

@app.post("/api/meaning")
def meaning():

    text = clean(
        request.form.get("word")
    )

    if not text:

        return jsonify({

            "answer":
                "Please enter a word or sentence."

        })


    low = text.lower().strip()


    # -----------------------------------------------------
    # DIRECT QUICK MEANING
    # -----------------------------------------------------

    if low in QUICK_MEANINGS:

        return jsonify({

            "answer":
                QUICK_MEANINGS[low]

        })


    # -----------------------------------------------------
    # REMOVE COMMON MEANING PHRASES
    # -----------------------------------------------------

    requested_text = text

    patterns = [

        r"^what does (.+?) mean\??$",

        r"^what is the meaning of (.+?)\??$",

        r"^meaning of (.+?)$",

        r"^define (.+?)$",

        r"^meaning (.+?)$",

    ]

    for pattern in patterns:

        match = re.match(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            requested_text = clean(
                match.group(1)
            )

            break


    requested_low = (
        requested_text
        .lower()
        .strip()
    )


    # -----------------------------------------------------
    # QUICK MEANING AFTER PATTERN
    # -----------------------------------------------------

    if requested_low in QUICK_MEANINGS:

        return jsonify({

            "answer":
                QUICK_MEANINGS[
                    requested_low
                ]

        })


    # -----------------------------------------------------
    # OLLAMA
    # -----------------------------------------------------

    prompt = f"""
You are Lumi, a friendly English language assistant.

The user wants to understand:

"{requested_text}"

Explain it in very simple English.

If it is a single word:
Give:
1. Simple meaning
2. One short example

If it is a sentence:
Explain the meaning of the whole sentence in simple English.
If there are difficult words, explain them briefly.

Rules:
- Use easy English.
- Be concise.
- Maximum 100 words.
- Do not mention AI, Ollama, APIs, servers, programming, or dictionaries.
"""

    answer = ask_ollama(
        prompt
    )

    if answer:

        return jsonify({

            "answer":
                answer

        })


    # -----------------------------------------------------
    # OLLAMA FAILED
    # -----------------------------------------------------

    return jsonify({

        "answer":
            "Lumi is temporarily unavailable. "
            "Please make sure Ollama is running "
            "and the configured model is available."

    })


# =========================================================
# GENERAL LUMI CHAT
# =========================================================

@app.post("/api/chat")
def chat():

    message = clean(
        request.form.get("message")
    )

    if not message:

        return jsonify({

            "answer":
                "Hi! I'm Lumi ✨ "
                "Ask me about a word or sentence."

        })


    low = message.lower().strip()


    # Direct meanings

    if low in QUICK_MEANINGS:

        return jsonify({

            "answer":
                QUICK_MEANINGS[low]

        })


    # Library count

    if MONGO_OK:

        try:

            if (
                "how many" in low
                and (
                    "book" in low
                    or "books" in low
                    or "library" in low
                )
            ):

                count = (
                    books.count_documents({})
                )

                return jsonify({

                    "answer":
                        f"You have {count} "
                        f"book"
                        f"{'s' if count != 1 else ''} "
                        f"in your library. 📚"

                })

        except Exception:
            pass


    # Library context

    library_context = (
        "(The library is currently empty.)"
    )

    if MONGO_OK:

        try:

            library_docs = list(

                books.find(

                    {},

                    {
                        "title": 1,
                        "genre": 1,
                        "status": 1,
                    },

                )
                .sort(
                    "_id",
                    -1
                )
                .limit(20)

            )

            if library_docs:

                library_context = "\n".join(

                    f"- "
                    f"{x.get('title', 'Untitled')} "
                    f"| genre: "
                    f"{x.get('genre', 'Other')} "
                    f"| status: "
                    f"{x.get('status', 'reading')}"

                    for x in library_docs

                )

        except Exception as e:

            print(
                "Library context error:",
                e
            )


    # Lumi prompt

    prompt = f"""
You are Lumi, the friendly assistant
inside My Mini Library.

You help with:

- Word meanings
- Sentence meanings
- Simple English explanations
- General questions
- Basic library questions

If the user asks about their library,
use ONLY the library data below.

Do not invent books.

If the user asks for a word meaning,
give a simple definition and one example.

If the user asks for a sentence meaning,
explain the complete sentence simply.

Keep answers short and friendly.

LIBRARY DATA:

{library_context}

USER:

{message}
"""

    answer = ask_ollama(
        prompt
    )

    if answer:

        return jsonify({

            "answer":
                answer

        })


    return jsonify({

        "answer":
            "Lumi is temporarily unavailable. "
            "Please make sure Ollama is running "
            "and the configured model is available."

    })


# =========================================================
# EDIT PAGE
# =========================================================

@app.route("/edit/<id>")
def edit_page(id):

    if not MONGO_OK:

        return (
            "MongoDB is not connected.",
            500
        )

    object_id = valid_object_id(id)

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    try:

        book = books.find_one({
            "_id": object_id
        })

        if not book:

            return redirect(
                url_for("index")
            )

        return render_template(

            "edit.html",

            book=serialize(book),

            genres=GENRES,

            stickers=STICKERS,

            app_name=APP_NAME,

        )

    except Exception as e:

        print(
            "Edit page error:",
            e
        )

        return (
            "Could not open edit page.",
            500
        )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    mongo_status = (
        "connected"
        if MONGO_OK
        else "disconnected"
    )

    ollama_status = "unknown"

    try:

        headers = {}

        if OLLAMA_API_KEY:

            headers["Authorization"] = (
                f"Bearer {OLLAMA_API_KEY}"
            )

        response = requests.get(

            f"{OLLAMA_URL.rstrip('/')}"
            "/api/tags",

            headers=headers,

            timeout=3,

        )

        if response.ok:

            ollama_status = "connected"

        else:

            ollama_status = "error"

    except Exception:

        ollama_status = "disconnected"


    return jsonify({

        "app":
            APP_NAME,

        "chatbot":
            CHATBOT_NAME,

        "flask":
            "running",

        "mongodb":
            mongo_status,

        "ollama":
            ollama_status,

        "model":
            OLLAMA_MODEL,

    })


# =========================================================
# FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def too_large(_):

    return jsonify({

        "error":
            f"PDF is too large. "
            f"Maximum upload size is "
            f"{MAX_UPLOAD_MB} MB."

    }), 413


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print("")
    print("======================================")
    print("          MY MINI LIBRARY")
    print("======================================")
    print("Chatbot:", "Lumi 📚✨")

    print(
        "MongoDB:",
        "CONNECTED"
        if MONGO_OK
        else "NOT CONNECTED"
    )

    print(
        "Ollama:",
        OLLAMA_URL
    )

    print(
        "Model:",
        OLLAMA_MODEL
    )

    print(
        "Website:",
        "http://127.0.0.1:5000"
    )

    print("======================================")
    print("")

    app.run(

        host="0.0.0.0",

        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        ),

        debug=False,

        use_reloader=False,

    )
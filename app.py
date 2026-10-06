import os
import re
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
    abort,
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

app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_UPLOAD_MB", "50")
) * 1024 * 1024


# =========================================================
# CHECK MONGODB CONFIG
# =========================================================

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI is missing. "
        "Please add your MongoDB Atlas connection string to .env"
    )


# =========================================================
# MONGODB
# =========================================================

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

                for book in books.find(
                    query
                )
                .sort(
                    "_id",
                    -1
                )
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
    )


# =========================================================
# ADD BOOK
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

        if (
            uploaded
            and uploaded.filename
        ):

            filename = (
                uploaded.filename
            )

            data = uploaded.read()

            file_id = fs.put(
                data,

                filename=filename,

                content_type=(
                    uploaded.mimetype
                    or "application/pdf"
                ),
            )

        books.insert_one(
            {
                "title": title,

                "genre": genre,

                "status": status,

                "sticker": sticker,

                "file_id": file_id,

                "filename": filename,

                "created_at":
                    datetime.utcnow(),
            }
        )

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

    object_id = valid_object_id(
        id
    )

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    update = {

        "title": clean(
            request.form.get(
                "title"
            )
        ),

        "genre": clean(
            request.form.get(
                "genre"
            )
        ) or "Other",

        "status": clean(
            request.form.get(
                "status"
            )
        ) or "reading",

        "sticker": clean(
            request.form.get(
                "sticker"
            )
        ) or "🌙",
    }

    try:

        old = books.find_one(
            {
                "_id":
                    object_id
            }
        )

        if not old:

            return (
                "Book not found.",
                404
            )

        uploaded = request.files.get(
            "pdf"
        )

        if (
            uploaded
            and uploaded.filename
        ):

            if old.get(
                "file_id"
            ):

                try:

                    fs.delete(
                        old[
                            "file_id"
                        ]
                    )

                except Exception:
                    pass

            data = uploaded.read()

            update[
                "file_id"
            ] = fs.put(
                data,

                filename=(
                    uploaded.filename
                ),

                content_type=(
                    uploaded.mimetype
                    or "application/pdf"
                ),
            )

            update[
                "filename"
            ] = uploaded.filename

        books.update_one(
            {
                "_id":
                    object_id
            },

            {
                "$set":
                    update
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

    object_id = valid_object_id(
        id
    )

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    try:

        book = books.find_one(
            {
                "_id":
                    object_id
            }
        )

        if (
            book
            and book.get("file_id")
        ):

            try:

                fs.delete(
                    book["file_id"]
                )

            except Exception:
                pass

        books.delete_one(
            {
                "_id":
                    object_id
            }
        )

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
# VIEW PDF
# =========================================================

@app.get("/read/<id>")
def read_pdf(id):
    if not MONGO_OK:
        return ("MongoDB is not connected.", 500)

    object_id = valid_object_id(id)
    if not object_id:
        return ("Invalid book ID.", 400)

    try:
        book = books.find_one({"_id": object_id})
        if not book:
            return ("Book not found.", 404)
        if not book.get("file_id"):
            return ("PDF not found.", 404)

        return render_template(
            "pdf.html",
            book=serialize(book),
        )
    except Exception as e:
        print("PDF reader error:", e)
        return ("Could not open PDF reader.", 500)


def _get_pdf_file(id):
    if not MONGO_OK:
        return None, None, ("MongoDB is not connected.", 500)

    object_id = valid_object_id(id)
    if not object_id:
        return None, None, ("Invalid book ID.", 400)

    try:
        book = books.find_one({"_id": object_id})
        if not book:
            return None, None, ("Book not found.", 404)
        if not book.get("file_id"):
            return None, None, ("PDF not found.", 404)

        return book, fs.get(book["file_id"]), None
    except Exception as e:
        print("PDF error:", e)
        return None, None, ("Could not read PDF.", 500)


@app.get("/pdf/<id>")
def pdf(id):
    book, file_data, error = _get_pdf_file(id)

    if error:
        return error

    filename = (
        book.get("filename")
        or "library.pdf"
    ).replace('"', "")

    response = send_file(
        BytesIO(file_data.read()),
        mimetype=(
            file_data.content_type
            or "application/pdf"
        ),
        download_name=filename,
        as_attachment=False,
        conditional=True,
        max_age=0,
    )

    response.headers["Content-Disposition"] = (
        f'inline; filename="{filename}"'
    )
    response.headers["Cache-Control"] = (
        "private, no-cache, no-store, must-revalidate"
    )
    response.headers["Accept-Ranges"] = "bytes"

    return response


@app.get("/download/<id>")
def download_pdf(id):
    book, file_data, error = _get_pdf_file(id)

    if error:
        return error

    return send_file(
        BytesIO(file_data.read()),
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
# OLLAMA
# =========================================================

def ask_ollama(prompt):

    try:

        headers = {
            "Content-Type": "application/json"
        }

        if OLLAMA_API_KEY:
            headers["Authorization"] = (
                f"Bearer {OLLAMA_API_KEY}"
            )

        response = requests.post(

            f"{OLLAMA_URL.rstrip('/')}/api/generate",

            headers=headers,

            json={

                "model":
                    OLLAMA_MODEL,

                "prompt":
                    prompt,

                "stream":
                    False,

                "options": {

                    "temperature":
                        0.2,

                    "num_predict":
                        180,
                },

                "keep_alive":
                    "10m",
            },

            timeout=45,
        )

        response.raise_for_status()

        data = response.json()

        answer = clean(
            data.get(
                "response"
            )
        )

        return (
            answer
            or
            "I couldn't generate a response right now."
        )

    except requests.RequestException as e:

        print(
            "Ollama error:",
            e
        )

        return None


# =========================================================
# WORD MEANING
# =========================================================

@app.post("/api/meaning")
def meaning():

    text = clean(
        request.form.get(
            "word"
        )
    )

    if not text:

        return jsonify({
            "answer":
                "Type a word or phrase first."
        })

    key = text.lower().strip()

    # -----------------------------------------------------
    # FAST BUILT-IN MEANINGS
    # -----------------------------------------------------

    quick_meanings = {

        "hard":
            "Difficult to do, understand, or deal with. "
            "Example: This is a hard question.",

        "easy":
            "Not difficult; something that can be done "
            "without much effort.",

        "entropy":
            "A measure of disorder or randomness in a system. "
            "In simple words, higher entropy means things are "
            "less organized or more spread out.",

        "disorder":
            "A lack of order or organization. "
            "Example: A messy room is in disorder.",

        "random":
            "Something that happens without a predictable "
            "pattern or specific order.",

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
    }

    # Instant response
    if key in quick_meanings:

        return jsonify({
            "answer":
                quick_meanings[key]
        })

    # -----------------------------------------------------
    # ONLINE DICTIONARY
    # Short timeout to keep application responsive
    # -----------------------------------------------------

    try:

        dictionary_url = (
            "https://api.dictionaryapi.dev/api/v2/"
            f"entries/en/"
            f"{requests.utils.quote(text)}"
        )

        response = requests.get(
            dictionary_url,
            timeout=2.5,
        )

        if response.ok:

            data = response.json()

            if (
                isinstance(
                    data,
                    list
                )
                and data
            ):

                definitions = []

                for meaning_item in data[0].get(
                    "meanings",
                    []
                )[:2]:

                    part = meaning_item.get(
                        "partOfSpeech",
                        ""
                    )

                    for definition in meaning_item.get(
                        "definitions",
                        []
                    )[:2]:

                        definition_text = clean(
                            definition.get(
                                "definition",
                                ""
                            )
                        )

                        if definition_text:

                            if part:

                                definitions.append(
                                    f"{part}: "
                                    f"{definition_text}"
                                )

                            else:

                                definitions.append(
                                    definition_text
                                )

                if definitions:

                    return jsonify({
                        "answer":
                            " ".join(
                                definitions
                            )
                    })

    except requests.RequestException as e:

        print(
            "Dictionary API unavailable:",
            e
        )

    except Exception as e:

        print(
            "Dictionary processing error:",
            e
        )

    # -----------------------------------------------------
    # OLLAMA FALLBACK
    # -----------------------------------------------------

    prompt = f"""
Give the meaning of the English word or phrase:

"{text}"

Rules:
- Give a simple English meaning.
- Give one short example sentence.
- Keep the answer under 80 words.
- Do not say you cannot find the word.
- Do not mention APIs or dictionaries.

Format:

Meaning: ...
Example: ...
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
    # FINAL FALLBACK
    # -----------------------------------------------------

    return jsonify({
        "answer":
            f'No meaning could be retrieved for '
            f'"{text}" right now. Please try again.'
    })


# =========================================================
# CHAT
# =========================================================

@app.post("/api/chat")
def chat():

    message = clean(
        request.form.get(
            "message"
        )
    )

    if not message:

        return jsonify({
            "answer":
                "Ask me about your library or "
                "anything you want to know."
        })

    # -----------------------------------------------------
    # FAST LIBRARY QUESTIONS
    # -----------------------------------------------------

    low = message.lower()

    if MONGO_OK:

        try:

            if (
                "how many" in low
                or "how much" in low
            ):

                count = (
                    books.count_documents({})
                )

                return jsonify({
                    "answer":
                        f"You have {count} "
                        f"item"
                        f"{'s' if count != 1 else ''} "
                        f"in your library."
                })

        except Exception:
            pass

    # -----------------------------------------------------
    # LIBRARY CONTEXT
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # OLLAMA PROMPT
    # -----------------------------------------------------

    prompt = f"""
You are a personal library assistant.

Answer clearly and briefly.

If the question is about the user's library,
use ONLY the library data below.

Do not invent books.

For general questions, answer normally.

Keep the answer concise.

LIBRARY DATA:
{library_context}

USER QUESTION:
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
            "Ollama is not responding. "
            "Please make sure Ollama is running "
            "and llama3.2:latest is installed."
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

    object_id = valid_object_id(
        id
    )

    if not object_id:

        return (
            "Invalid book ID.",
            400
        )

    try:

        book = books.find_one(
            {
                "_id":
                    object_id
            }
        )

        if not book:

            return redirect(
                url_for("index")
            )

        return render_template(

            "edit.html",

            book=serialize(
                book
            ),

            genres=GENRES,

            stickers=STICKERS,
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

        "flask":
            "running",

        "mongodb":
            mongo_status,

        "ollama":
            ollama_status,

        "model":
            OLLAMA_MODEL,
    })


@app.errorhandler(413)
def too_large(_):
    return jsonify({
        "error":
            "PDF is too large. Maximum upload size is 50 MB."
    }), 413


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    print("")

    print(
        "======================================"
    )

    print(
        "      MY MINI LIBRARY"
    )

    print(
        "======================================"
    )

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

    print(
        "======================================"
    )

    print("")

    app.run(

        host="0.0.0.0",

        port=int(os.getenv("PORT", "5000")),

        debug=False,

        use_reloader=False,
    )
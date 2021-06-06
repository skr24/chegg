import requests
from requests.auth import HTTPBasicAuth
from pprint import pprint
import secrets
import uuid
from urllib.parse import urlparse
from flask import Flask, jsonify, render_template, request, abort, redirect
from collections import deque

s = requests.Session()
s.auth = HTTPBasicAuth('hlDpZAPF05mqjAmg7cqtIKLOhUryB8p1', 'uBjzakmxGx6WtqAr')
s.headers.update({
    'X-CHEGG-DEVICEID': secrets.token_hex(8),
    'X-CHEGG-SESSIONID': str(uuid.uuid4()),
    #'X-CHEGG-XYZPASS': '1',
    'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; Pixel XL Build/PPR1.180610.009)'
    })

tbs_recent_books = deque(maxlen=10)
tbs_books = {}
tbs_chapters = {}
tbs_problems = {}

def get_tbs_books(query):
    r = s.get('https://hub.chegg.com/v1/book', params={
        'q': query, 'f.hasSolutions': true
        })
    r.raise_for_status()
    return r.json()

def get_tbs_book(book_id):
    if book_id in tbs_books:
        return tbs_books[book_id]

    output = []

    r = s.get(f'https://hub.chegg.com/v1/book/{book_id}')
    if r.status_code == 404:
        return None

    r.raise_for_status()

    j = r.json()
    result = j['result']

    output = {
        'id': book_id,
        'name': result['title'],
        'full_name': result['fullTitle'],
        'edition': result['edition'],
        'image': result['imgLarge'] if 'imgLarge' in result else result['imgThumb'],
        'has_solutions': result['hasSolutions']
    }

    if book_id not in tbs_recent_books:
        tbs_recent_books.append(book_id)

    tbs_books[book_id] = output
    return output


def get_tbs_chapters(book_id, offset=0, all=True):
    if book_id in tbs_chapters:
        return tbs_chapters[book_id]

    output = []

    r = s.get(f'https://hub.chegg.com/v1/book/{book_id}/chapters', params={
        'offset': offset
        })
    r.raise_for_status()
    j = r.json()

    output.extend(j['result'])

    while all and 'nextPage' in j:
        r = s.get(j['nextPage'])
        r.raise_for_status()
        j = r.json()

        output.extend(j['result'])
    
    tbs_chapters[book_id] = output
    return output

def get_tbs_problems(chapter_id, offset=0, all=True):
    if chapter_id in tbs_problems:
        return tbs_problems[chapter_id]

    output = []

    r = s.get(f'https://hub.chegg.com/v1/chapter/{chapter_id}/problems', params={
        'offset': offset
        })
    r.raise_for_status()
    j = r.json()

    output.extend(j['result'])

    while all and 'nextPage' in j:
        r = s.get(j['nextPage'])
        r.raise_for_status()
        j = r.json()

        output.extend(j['result'])
    
    tbs_problems[chapter_id] = output
    return output

def get_tbs_problem_text(problem_id):
    r = s.get(f'https://hub.chegg.com/content/tbs-problem/{problem_id}.html')
    if r.status_code == 404:
        return None
    r.raise_for_status()

    return r.text

def get_tbs_solutions(problem_id):
    r = s.get(f'https://hub.chegg.com/v1/problem/{problem_id}/solutions')
    r.raise_for_status()
    j = r.json()

    return j['result']

def load_solutions(problem_id):
    solutions = get_tbs_solutions(problem_id)

    output = []

    for solution in solutions:
        solution_output = []
        steps = solutions[0]['steps']
        for i, step in enumerate(steps):
            r = s.get(step['link'])
            solution_output.append({
                'i': i + 1,
                'text': r.text
                })
        output.append({
            'num_steps': len(steps),
            'steps': solution_output
            })

    return output

def load_problems(chapter_id):
    problems = get_tbs_problems(chapter_id)

    output = []

    for problem in problems:
        output.append({
            'name': problem['name'],
            'id': problem['id']
            })

    return output


def load_chapters(book_id):
    chapters = get_tbs_chapters(book_id)

    output = []

    for chapter in chapters:
        output.append({
            'name': chapter['name'],
            'id': chapter['id']
            })

    return output


app = Flask(__name__)

@app.route('/book/<int:book_id>/chapters')
def get_chapters(book_id):
    return jsonify(get_tbs_chapters(book_id))

@app.route('/chapter/<int:chapter_id>/problems')
def get_problems(chapter_id):
    return jsonify(get_tbs_problems(chapter_id))

@app.route('/problem/<int:problem_id>')
def get_problem(problem_id):
    r = s.get(f'https://hub.chegg.com/content/tbs-problem/{problem_id}.html')
    return r.text if r.status_code is 200 else ''

@app.route('/problem/<int:problem_id>/solutions')
def get_solutions(problem_id):
    return jsonify(load_solutions(problem_id))


@app.route('/')
def request_index():
    recent_books = [tbs_books[book_id] for book_id in tbs_recent_books]
    return render_template('chegg.html', recent_books=recent_books)

@app.route('/query', methods=['POST'])
def request_query():
    query = request.form['query']
    path = urlparse(query).path
    if path.startswith('/homework-help/questions-and-answers/'):
        question_id = path.split('q')[-1]
        return redirect(f'/qna/{question_id}', 302)
    elif path.startswith('/homework-help/'):
        book_id = path.split('-')[-1]
        return redirect(f'/tbs/{book_id}', 302)
    abort(501)

@app.route('/tbs/<int:book_id>')
def request_tbs_book(book_id):
    current = {
        'book': {
            'id': book_id
        }
    }

    return render_template('chegg.html', current=current, book=get_tbs_book(book_id),
        chapters=load_chapters(book_id))

@app.route('/tbs/<int:book_id>/<int:chapter_id>')
def request_tbs_chapter(book_id, chapter_id):
    chapters = get_tbs_chapters(book_id)
    chapter_info = next((item for item in chapters if item['id'] == str(chapter_id)))

    current = {
        'chapter': {
            'name': chapter_info['name'],
            'id': chapter_id
        },
        'book': {
            'id': book_id
        }
    }

    return render_template('chegg.html', current=current, book=get_tbs_book(book_id),
        chapters=load_chapters(book_id), problems=load_problems(chapter_id))

@app.route('/tbs/<int:book_id>/<int:chapter_id>/<int:problem_id>')
def request_tbs_problem(book_id, chapter_id, problem_id):
    problems = get_tbs_problems(chapter_id)
    problem_info = next((item for item in problems if item['id'] == str(problem_id)))
    problem_text = get_tbs_problem_text(problem_id)

    chapters = get_tbs_chapters(book_id)
    chapter_info = next((item for item in chapters if item['id'] == str(chapter_id)))

    solutions = load_solutions(problem_id)

    current = {
        'problem': {
            'name': problem_info['name'],
            'id': problem_id
        },
        'chapter': {
            'name': chapter_info['name'],
            'id': chapter_id
        },
        'book': {
            'id': book_id
        }
    }

    return render_template('chegg.html', current=current, book=get_tbs_book(book_id),
        chapters=load_chapters(book_id), problems=load_problems(chapter_id),
        problem_text=problem_text, solutions=solutions)
  
# main.py
# A2-3115004 - Twitter/X Clone
# FastAPI + MongoDB + Firebase Auth + Azurite

import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token
from google.auth.transport import requests
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import starlette.status as status
from datetime import datetime, timedelta
from bson import ObjectId
from azure.storage.blob import BlobServiceClient, AccessPolicy, ContainerSasPermissions, PublicAccess
from dotenv import load_dotenv
import uvicorn
import certifi

load_dotenv()

# ── MongoDB connection ────────────────────────────────────────────────────
# Replace with YOUR MongoDB Atlas connection string
uri = os.getenv('MONGODB_URI')
if not uri:
    raise RuntimeError('MONGODB_URI is not set. Copy .env.example to .env and add your MongoDB Atlas connection string.')


client = MongoClient(
    uri,
    server_api=ServerApi('1'),
    tls=True,
    tlsCAFile=certifi.where()
)
try:
    client.admin.command('ping')
    print("Connected to MongoDB!")
except Exception as e:
    print(e)

# ── Database: A2-3115004 (as required by assignment) ─────────────────────
db               = client['A2-3115004']
user_collection  = db['users']
Claw_collection = db['Claws']

# ── Azurite (Azure Blob Storage) ──────────────────────────────────────────
azure_connection_string = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

azure_service_client = BlobServiceClient.from_connection_string(azure_connection_string)
azure_container_name  = "twitter-images"

azure_container_client = azure_service_client.get_container_client(azure_container_name)
try:
    azure_container_client.create_container()
except Exception:
    print('container exists')

try:
    access_policy = AccessPolicy(
        permission=ContainerSasPermissions(read=True),
        expiry=datetime.now() + timedelta(hours=24),
        start=datetime.now() - timedelta(minutes=1)
    )
    identifiers = {'read': access_policy}
    azure_container_client.set_container_access_policy(
        signed_identifiers=identifiers,
        public_access=PublicAccess.CONTAINER
    )
except Exception as e:
    print(e)

# ── FastAPI app ───────────────────────────────────────────────────────────
app = FastAPI()
firebase_request_adapter = requests.Request()

app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory="templates")


# ── Helper: validate Firebase token ──────────────────────────────────────
def validateFirebaseToken(id_token):
    if not id_token:
        return None
    user_token = None
    try:
        user_token = google.oauth2.id_token.verify_firebase_token(
            id_token, firebase_request_adapter)
    except ValueError as err:
        print(str(err))
    return user_token


# ── Helper: get or create user document ──────────────────────────────────
def getUser(user_token):
    user = user_collection.find_one({'user_id': user_token['user_id']})
    if not user:
        user_dict = {
            'user_id':   user_token['user_id'],
            'email':     user_token['email'],
            'username':  '',
            'bio':       '',
            'photo_url': '',
            'following': [],
            'followers': []
        }
        user_collection.insert_one(user_dict)
        user = user_collection.find_one({'user_id': user_token['user_id']})
    return user


# ══════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════

# ── Home / Timeline ───────────────────────────────────────────────────────
@app.get('/', response_class=HTMLResponse)
async def root(request: Request):
    id_token      = request.cookies.get('token')
    user_token    = validateFirebaseToken(id_token)
    error_message = None

    if not user_token:
        return templates.TemplateResponse('login.html',
            {'request': request})

    user = getUser(user_token)

    # If no username set yet, redirect to setup page
    if not user['username']:
        return RedirectResponse('/setup-username')

    # Build timeline: own Claws + Claws from people user follows
    following_list = user.get('following', [])
    timeline_users = following_list + [user['user_id']]

    Claws = list(Claw_collection.find(
        {'user_id': {'$in': timeline_users}}
    ).sort('created_at', -1).limit(20))

    # Attach author info to each Claw
    for Claw in Claws:
        author = user_collection.find_one({'user_id': Claw['user_id']})
        Claw['author_username'] = author['username'] if author else 'unknown'
        Claw['author_photo']    = author.get('photo_url', '') if author else ''
        Claw['is_Claw']      = Claw.get('is_Claw', False)
        Claw['_id_str']         = str(Claw['_id'])

    return templates.TemplateResponse('feed.html', {
        'request':    request,
        'user':       user,
        'Claws':     Claws,
        'error':      error_message
    })


# ── Username setup (first login) ──────────────────────────────────────────
@app.get('/setup-username', response_class=HTMLResponse)
async def setupUsernameGet(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')
    return templates.TemplateResponse('setup_username.html',
        {'request': request, 'error': None})


@app.post('/setup-username', response_class=RedirectResponse)
async def setupUsernamePost(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form     = await request.form()
    username = form['username'].strip()

    if not username:
        return templates.TemplateResponse('setup_username.html',
            {'request': request, 'error': 'Username cannot be empty'})

    # Check uniqueness
    existing = user_collection.find_one({'username': username})
    if existing:
        return templates.TemplateResponse('setup_username.html',
            {'request': request, 'error': 'Username already taken, choose another'})

    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$set': {'username': username}}
    )
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# ── Post a Claw ──────────────────────────────────────────────────────────
@app.post('/post-Claw', response_class=RedirectResponse)
async def postClaw(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form    = await request.form()
    content = form['content'].strip()

    if not content or len(content) > 280:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    image_url = ''
    image_file = form.get('image')
    if image_file and image_file.filename != '':
        ext = image_file.filename.rsplit('.', 1)[-1].lower()
        if ext in ['jpg', 'jpeg', 'png']:
            blob_name = f"{user_token['user_id']}/{datetime.now().timestamp()}.{ext}"
            azure_container_client.upload_blob(
                name=blob_name,
                data=image_file.file.read(),
                overwrite=True
            )
            blob_client = azure_container_client.get_blob_client(blob=blob_name)
            image_url   = blob_client.url

    Claw = {
        'user_id':    user_token['user_id'],
        'content':    content,
        'image_url':  image_url,
        'created_at': datetime.now(),
        'is_Claw': False,
        'Claw_of': None
    }
    Claw_collection.insert_one(Claw)
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# ── Edit Claw ────────────────────────────────────────────────────────────
@app.post('/edit-Claw', response_class=RedirectResponse)
async def editClaw(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form       = await request.form()
    Claw_id   = form['Claw_id']
    content    = form['content'].strip()

    if not content or len(content) > 280:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    image_url  = None
    image_file = form.get('image')
    if image_file and image_file.filename != '':
        ext = image_file.filename.rsplit('.', 1)[-1].lower()
        if ext in ['jpg', 'jpeg', 'png']:
            blob_name = f"{user_token['user_id']}/{datetime.now().timestamp()}.{ext}"
            azure_container_client.upload_blob(
                name=blob_name,
                data=image_file.file.read(),
                overwrite=True
            )
            blob_client = azure_container_client.get_blob_client(blob=blob_name)
            image_url   = blob_client.url

    update_fields = {'content': content}
    if image_url:
        update_fields['image_url'] = image_url

    Claw_collection.update_one(
        {'_id': ObjectId(Claw_id), 'user_id': user_token['user_id']},
        {'$set': update_fields}
    )
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# ── Delete Claw ──────────────────────────────────────────────────────────
@app.post('/delete-Claw', response_class=RedirectResponse)
async def deleteClaw(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form     = await request.form()
    Claw_id = form['Claw_id']

    Claw_collection.delete_one(
        {'_id': ObjectId(Claw_id), 'user_id': user_token['user_id']}
    )
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# ── Claw ───────────────────────────────────────────────────────────────
@app.post('/Claw', response_class=RedirectResponse)
async def Claw(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form     = await request.form()
    Claw_id = form['Claw_id']

    original = Claw_collection.find_one({'_id': ObjectId(Claw_id)})
    if not original:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    Claw_doc = {
        'user_id':          user_token['user_id'],
        'content':          original['content'],
        'image_url':        original.get('image_url', ''),
        'created_at':       datetime.now(),
        'is_Claw':       True,
        'Claw_of':       str(original['_id']),
        'original_user_id': original['user_id']
    }
    Claw_collection.insert_one(Claw_doc)
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


# ── Profile page ──────────────────────────────────────────────────────────
@app.get('/profile/{username}', response_class=HTMLResponse)
async def profile(request: Request, username: str):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    current_user   = getUser(user_token)
    profile_user   = user_collection.find_one({'username': username})

    if not profile_user:
        return RedirectResponse('/')

    is_following = profile_user['user_id'] in current_user.get('following', [])

    Claws = list(Claw_collection.find(
        {'user_id': profile_user['user_id']}
    ).sort('created_at', -1).limit(10))

    for Claw in Claws:
        Claw['_id_str'] = str(Claw['_id'])
        if Claw.get('is_Claw'):
            orig_author = user_collection.find_one(
                {'user_id': Claw.get('original_user_id', '')})
            Claw['original_author'] = orig_author['username'] if orig_author else 'unknown'

    return templates.TemplateResponse('profile.html', {
        'request':      request,
        'current_user': current_user,
        'profile_user': profile_user,
        'Claws':       Claws,
        'is_following': is_following
    })


# ── Follow user ───────────────────────────────────────────────────────────
@app.post('/follow', response_class=RedirectResponse)
async def followUser(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form            = await request.form()
    target_user_id  = form['target_user_id']
    redirect_url    = form.get('redirect_url', '/')

    # Add to current user's following list
    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$addToSet': {'following': target_user_id}}
    )
    # Add to target user's followers list
    user_collection.update_one(
        {'user_id': target_user_id},
        {'$addToSet': {'followers': user_token['user_id']}}
    )
    return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)


# ── Unfollow user ─────────────────────────────────────────────────────────
@app.post('/unfollow', response_class=RedirectResponse)
async def unfollowUser(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form           = await request.form()
    target_user_id = form['target_user_id']
    redirect_url   = form.get('redirect_url', '/')

    user_collection.update_one(
        {'user_id': user_token['user_id']},
        {'$pull': {'following': target_user_id}}
    )
    user_collection.update_one(
        {'user_id': target_user_id},
        {'$pull': {'followers': user_token['user_id']}}
    )
    return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)


# ── Search ────────────────────────────────────────────────────────────────
@app.get('/search', response_class=HTMLResponse)
async def search(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    current_user = getUser(user_token)
    query        = request.query_params.get('q', '').strip()
    search_type  = request.query_params.get('type', 'users')

    user_results  = []
    Claw_results = []

    if query:
        if search_type == 'users':
            user_results = list(user_collection.find(
                {'username': {'$regex': f'^{query}', '$options': 'i'}}
            ).limit(20))
        else:
            Claw_results = list(Claw_collection.find(
                {'content': {'$regex': f'^{query}', '$options': 'i'}}
            ).sort('created_at', -1).limit(20))
            for Claw in Claw_results:
                author = user_collection.find_one({'user_id': Claw['user_id']})
                Claw['author_username'] = author['username'] if author else 'unknown'
                Claw['author_photo']    = author.get('photo_url', '') if author else ''
                Claw['_id_str']         = str(Claw['_id'])

    return templates.TemplateResponse('search.html', {
        'request':      request,
        'current_user': current_user,
        'query':        query,
        'search_type':  search_type,
        'user_results': user_results,
        'Claw_results':Claw_results
    })


# ── Edit profile (bio + photo) ────────────────────────────────────────────
@app.post('/edit-profile', response_class=RedirectResponse)
async def editProfile(request: Request):
    id_token   = request.cookies.get('token')
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        return RedirectResponse('/')

    form = await request.form()
    bio  = form.get('bio', '').strip()

    update_fields = {}
    if len(bio) <= 280:
        update_fields['bio'] = bio

    image_file = form.get('photo')
    if image_file and image_file.filename != '':
        ext = image_file.filename.rsplit('.', 1)[-1].lower()
        if ext in ['jpg', 'jpeg', 'png']:
            blob_name = f"avatars/{user_token['user_id']}.{ext}"
            azure_container_client.upload_blob(
                name=blob_name,
                data=image_file.file.read(),
                overwrite=True
            )
            blob_client              = azure_container_client.get_blob_client(blob=blob_name)
            update_fields['photo_url'] = blob_client.url

    if update_fields:
        user_collection.update_one(
            {'user_id': user_token['user_id']},
            {'$set': update_fields}
        )

    user = getUser(user_token)
    return RedirectResponse(
        f"/profile/{user['username']}",
        status_code=status.HTTP_302_FOUND
    )


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
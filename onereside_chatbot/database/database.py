from pymongo import MongoClient

from onereside_chatbot.utils.env_load import mongo_uri

client = MongoClient(mongo_uri)
db = client["pacific"]

from pymongo import MongoClient

from onereside_chatbot.utils.env_load import mongo_prod_db_name, mongo_uri

client = MongoClient(mongo_uri)
db = client[mongo_prod_db_name]

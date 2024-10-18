# Copyright (c) 2024, zaviago and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from marketplace_integration.marketplace.lazada_api import LazadaClient
from datetime  import datetime

import json

class LazadaItems(Document):
	
	# DATA = {
	# "New data roduct":{
	# 	"name": "New data roduct",
	# 	"product_name": "New Product",
	# 	"description": "Hello world, this is a new prodcut for all of us",
	# 	"image": "https://thisimage.com/hell",
	# 	"created_at": datetime.now(),
	# 	"updated_at": datetime.now()
	# },
    # "New product":{
    # 	"name": "New product",
	# 	"product_name": "New Product",
	# 	"description": "Hello world, this is a new prodcut for all of us",
	# 	"image": "https://thisimage.com/hell",
	# 	"created_at": datetime.now(),
	# 	"updated_at": datetime.now()
	# },
    # "New for old product":{
    # 	"name": "New for old product",
	# 	"product_name": "New Product",
	# 	"description": "Hello world, this is a new prodcut for all of us",
	# 	"image": "https://thisimage.com/hell",
	# 	"created_at": datetime.now(),
	# 	"updated_at": datetime.now()
	# }}
	client = LazadaClient("https://api.lazada.co.th/rest")

	@staticmethod
	def fetch_data():
		result = LazadaItems.client.get_products({}).get("data")
		processed_data = {}
		for item in result["products"]:
			item_attributes = item.get("attributes")
			product_name = item_attributes.get("name")
			try:
				print(int(item.get("created_time")))
				product = {
					"created_at": datetime.fromtimestamp(int(item.get("created_time"))/1000),
					"updated_at": datetime.fromtimestamp(int(item.get("updated_time"))/1000),
					"images": item.get("images")[0],
					"description": item_attributes.get("description"),
					"name": product_name,
					"product_name": product_name
				}
				processed_data[product_name] = product
			except Exception as e:
				print(e)

		return processed_data
		
	def db_insert(self, *args, **kwargs):
		pass

	def load_from_db(self):
		d = LazadaItems.DATA.get(self.name)
		super(Document, self).__init__(d)

	def db_update(self):
		pass

	def delete(self):
		pass

	@staticmethod
	def get_list(args):

		DATA = LazadaItems.fetch_data()

		return [frappe._dict(doc) for name, doc in DATA.items()]

	@staticmethod
	def get_count(args):
		pass

	@staticmethod
	def get_stats(args):
		pass


# Copyright (c) 2024, zaviago and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from marketplace_integration.marketplace.lazada_api import LazadaClient
from marketplace_integration.marketplace.lazada_manager import lazada_manager
from datetime  import datetime

import json

class LazadaItems(Document):

	def db_insert(self, *args, **kwargs):
		pass
	
	def get_skus(self, product_name):
		return self.products.get(product_name).get("skus")

	def load_from_db(self):
		d = lazada_manager.get_product(self.name)
		super(Document, self).__init__(d)

	def db_update(self):
		pass

	def delete(self):
		pass

	@staticmethod
	def get_list(args):
		DATA = lazada_manager.get_list()
		return [frappe._dict(doc) for name, doc in DATA.items()]

	@staticmethod
	def get_count(args):
		return lazada_manager.get_count()

	@staticmethod
	def get_stats(args):
		pass


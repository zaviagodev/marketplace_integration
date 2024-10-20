# Copyright (c) 2024, zaviago and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from marketplace_integration.marketplace.lazada_manager import lazada_manager


class LazadaSKUs(Document):		
	def db_insert(self, *args, **kwargs):
		pass

	def load_from_db(self):
		print("CALLED THIS LOAD_from_db")
		pass

	def db_update(self):
		pass

	def delete(self):
		pass

	@staticmethod
	def get_list(args):
		print("CALLED THIS LOAD_from_db")
		pass

	@staticmethod
	def get_count(args):
		return lazada_manager.get_count()

	@staticmethod
	def get_stats(args):
		pass

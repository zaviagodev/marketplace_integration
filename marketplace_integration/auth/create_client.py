# Copyright (c) 2023, Zaviago and contributors
# For license information, please see license.txt

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
import frappe
from frappe import _
from frappe.utils import cint, cstr, get_datetime
from pytz import timezone
import requests
import json
import webbrowser
from marketplace_integration.lazada import LazopClient, LazopRequest


@frappe.whitelist()
def receive_code_from_shopee(code,shop_id):
	site_name = frappe.utils.get_url()
	params = {'code' :code,'shop_id' : shop_id,'site_name' : site_name }
	url = "https://templete.zaviago.com/api/method/marketplace_management.auth.create_client.code_to_token_auth_shopee"
	response = requests.post(url,params)
	response = json.loads(response.text)
	access_token = response["message"]["access_token"]
	refresh_token = response["message"]["new_refresh_token"]
 
	if access_token and refresh_token:
		doc = frappe.get_doc('Marketplace integration')
		doc.active_shopee=1
		doc.access_token=access_token
		doc.refresh_token_copy=refresh_token
		doc.shopee_code=code
		doc.shop_id=shop_id
		doc.save(
             ignore_permissions=True,
             ignore_version=True
        )
		frappe.db.commit()
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/desk"

@frappe.whitelist()
def receive_code_from_lazada(code):
	client = LazopClient('https://api.lazada.com/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
	request = LazopRequest('/auth/token/create')
	request.add_api_param('code', code)
	response = client.execute(request)
	response = response.body

	access_token = response["access_token"]
	refresh_token = response["refresh_token"]

	if access_token and refresh_token:
		doc = frappe.get_doc('Marketplace integration')
		doc.active_lazada = 1
		doc.lazada_access_token = access_token
		doc.lazada_refresh_token = refresh_token
		doc.lazada_seller_id = response['country_user_info'][0]['seller_id']
		doc.save(
             ignore_permissions=True,
             ignore_version=True
        )
		frappe.db.commit()
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = "/desk"
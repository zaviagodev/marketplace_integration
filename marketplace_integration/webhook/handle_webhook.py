import frappe
import requests
from frappe import _
from frappe.utils import cint, cstr, get_datetime
import json
import hashlib
import time
from urllib.parse import quote
import urllib.parse
from marketplace_integration.lazada import LazopClient, LazopRequest
from datetime import datetime
from erpnext.selling.doctype.sales_order.sales_order import create_pick_list,make_sales_invoice
from erpnext.stock.doctype.pick_list.pick_list import create_delivery_note
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from datetime import datetime, timedelta

@frappe.whitelist(allow_guest=True)
def test_shopee_webhook():
   return frappe.get_doc("Marketplace integration")
   return getorderaddional_data("240309K0SYSG3K", token, shop_id)

@frappe.whitelist(allow_guest=True)
def push_shopee_webhook(ordersn,shop_id,status):
    try:
        existing_record = frappe.get_doc("Marketplace Logs", {"order_id": ordersn, "status": status})
    except frappe.DoesNotExistError:
        existing_record = None
    
    if not existing_record:
        contact = frappe.new_doc("Marketplace Logs")
        contact.order_id = ordersn
        contact.status = status
        contact.shope_id = shop_id
        contact.marketplace = "Shopee"
        contact.insert(ignore_permissions=True)

@frappe.whitelist(allow_guest=True)
def push_shopee_lazada(ordersn,shop_id,status,buyer_id):
    try:
        existing_record = frappe.get_doc("Marketplace Logs", {"order_id": ordersn, "status": status})
    except frappe.DoesNotExistError:
        existing_record = None
    
    # if not existing_record:
    #     contact = frappe.new_doc("Marketplace Logs")
    #     contact.order_id = ordersn
    #     contact.status = status
    #     contact.shope_id = shop_id
    #     contact.buyer_id = buyer_id
    #     contact.marketplace = "Lazada"
    #     contact.insert(ignore_permissions=True)
        
    connect = LazadaMarketplaceClient()	
    sales_order =  connect.handle_lazada_order_status ( ordersn,shop_id,status,buyer_id)
    return sales_order
        # contact.sale_order = sales_order
        # contact.save(ignore_permissions=True)
      

class LazadaMarketplaceClient:
    def handle_lazada_order_status( self, ordersn,shop_id,status,buyer_id):
        order_info =  self.get_order_info(ordersn)
        if order_info:
            order_details_json = json.loads(order_info.get('order_details', '[]'))
            order_items = json.loads(order_info.get('order_items', '[]'))
            order_details = order_details_json.get('data', '[]')
            order_items = order_items.get('data', '[]')

            customer_key = self.inser_customer(order_details,buyer_id)
            product = self.check_product_sku(order_items)
            

            if product:
                frappe.set_user("Administrator")  
                
                sale_order = self.create_sales_order(order_details,order_items,customer_key)
                if status == 'pending':
                    self.create_pack_list(sale_order)
                elif  status == 'ready_to_ship' or status == 'ready_to_ship_pending':
                    self.create_delivery_note(sale_order)
                    self.create_sales_invoice(sale_order)   
                elif  status == 'delivered':
                    self.create_payment_entry(ordersn)
                    self.create_purchase_invoice_lazada(ordersn)

            else:
                self.create_order_issue(order_details,order_items,customer_key)
            
    def create_purchase_invoice_lazada(self, ordersn):
        expenss = self.getorderdetails_addional_expenss(ordersn)
        
        paymentfee = self.get_amount_by_fee_type(expenss,"3")
        commission = float(self.get_amount_by_fee_type(expenss,"16"))
        freeshipmax = float(self.get_amount_by_fee_type(expenss,"298"))
        lcpfee = float(self.get_amount_by_fee_type(expenss,"304"))
        subcide = float(self.get_amount_by_fee_type(expenss,"1028"))       
        commission = paymentfee+commission+freeshipmax+lcpfee
        
        try:
             existing_doc = frappe.get_doc("Purchase Invoice", {"marketplace_order_number": ordersn})
             return existing_doc.name
        except frappe.DoesNotExistError:
            new_invoice = frappe.new_doc('Purchase Invoice')
            new_invoice.supplier = "Lazada Co., Ltd",
            new_invoice.owner_department = "API Admin - Clinton"
            new_invoice.marketplace_order_number = ordersn
            new_invoice.append("items", {
                "item_code": "1234",
                "item_name": "Total Fees and Service Charges",
                "rate" : commission,
                "qty": 1
            })
            new_invoice.append("items", {
                "item_code": "1234",
                "item_name": "Total Delivery Fee",
                "rate" : subcide,
                "qty": 1
            })
            new_invoice.save()
            new_invoice.submit()
            doc = get_payment_entry("Purchase Invoice", new_invoice.name)
            olddate = datetime.now()
            olddate_str = olddate.strftime("%Y-%m-%d")
            doc.reference_no = ordersn
            doc.reference_date = olddate_str
            doc.mode_of_payment = "Lazada Fee"
            doc.save(ignore_permissions=True)
            doc.submit()
            
            frappe.db.commit()
            

        
        

    
    def get_amount_by_fee_type(self, data, fee_type):
        amounts = [entry['amount'] for entry in data if entry.get('fee_type') == fee_type]
        if amounts:
            return abs(float(amounts[0]))
        else:
            return 0 





    def create_payment_entry(self, ordersn):
        try:
            sales_invoice = frappe.get_doc("Sales Invoice", {"marketplace_order_number": ordersn})
            doc = get_payment_entry("Sales Invoice", sales_invoice.name)
            doc.save(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass

    def create_sales_invoice(self, order_details, order_items, customkey):
        doc = make_sales_invoice("SAL-ORD-2024-00042",ignore_permissions=True)
        doc.custom_channel = "Lazada"
        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc
    
    
    def create_delivery_note(self, sale_order):
        try:
            picklist = frappe.get_doc("Pick List", {"sales_order": sale_order})
            doc = create_delivery_note(picklist.name)
            doc.save(ignore_permissions=True)
            doc.submit()
            frappe.db.commit()
            return doc
        except frappe.DoesNotExistError:
            pass
        
    def create_pack_list(self,sale_order):
        doc = create_pick_list(sale_order)
        doc.save(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()
        return doc
    
    
    def create_sales_order(self, order_details, order_items, customkey):
        try:
            existing_doc = frappe.get_doc("Sales Order", {"marketplace_order_number": order_details['order_number']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Sales Order')
            new_order.customer = customkey
            new_order.delivery_date = datetime.now().date()
            new_order.marketplace_order_number = order_details.get('order_number', '')

            platform_voucher = 0
            seller_voucher = 0
            discounttotal = 0

            #$totalz = $order["price"]+$shipping_price;
            

            
            taxs = self.get_listof_taxs()

            for item in order_items:
                new_order.append("items", {
                    "item_code": item['sku'],
                    "rate" : item['item_price'],
                    "price": item['item_price'],
                    "amount": item['item_price'],
                    "base_rate": item['item_price'],
                    "base_amount": item['item_price'],
                    "stock_uom_rate": item['item_price'],
                    "net_rate": item['item_price'],
                    "net_amount": item['item_price'],
                    "base_net_rate": item['item_price'],
                    "base_net_amount": item['item_price'],
                    "qty": 1
                })
                platform_voucher += item.get('voucher_platform', 0)
                seller_voucher += item.get('voucher_seller', 0)
                discounttotal += item.get('voucher_amount', 0)
                

            ordertotal = float(order_details["price"]) + float(order_details["shipping_fee"])
            grand_total_marketplace = ordertotal-discounttotal

        


            if seller_voucher:
                new_order.append("custom_seller_voucher",{
                    "doctype": 'Seller Voucher List',
                    "voucher_name": 'Seller Discount',
                    "voucher_amount": seller_voucher
                })


            for item in taxs:
                new_order.append("taxes",item)

            new_order.disable_rounded_total = 1
            if platform_voucher:
                new_order.custom_marketplace_discount = platform_voucher


            new_order.custom_grand_total_marketplace = grand_total_marketplace
            new_order.discount_amount = seller_voucher
            new_order.custom_marketplace_taxes_and_charges = float(order_details["shipping_fee"])
            new_order.taxes_and_charges = 'Thailand Tax - Clinton'



            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Lazada"

            new_order.insert(ignore_permissions=True)
            new_order.submit()
            frappe.db.commit()
            return new_order.name


    def get_listof_taxs(self):
        doc = frappe.get_doc("Sales Taxes and Charges Template","Thailand Tax - Clinton")
        taxs = doc.taxes
        return taxs

    def map_sales_order_to_pick_list(self,source_name):
        new_picl_list = frappe.new_doc('Pick List')
        new_picl_list.parent_warehouse = "HQ (คลังหลัก) - Clinton"
        new_picl_list.company = "CLINTON INTERTRADE COMPANY LIMITED"
        new_picl_list.marketplace_platform = "Lazada"
        new_picl_list.marketplace_order_number = "123123123"
        new_picl_list.insert(ignore_permissions=True)
        return new_picl_list


    def create_order_issue(self, order_details, order_items, customkey):
        try:
            existing_doc = frappe.get_doc("Marketplace order Issue", {"marketplace_order_number": order_details['order_number']})
            return existing_doc.name
        except frappe.DoesNotExistError:
            new_order = frappe.new_doc('Marketplace order Issue')
            new_order.customer = customkey
            new_order.due_date = datetime.now().date()
            new_order.marketplace_order_number = order_details.get('order_number', '')
            for item in order_items:
                new_order.append("items",{
                    "item": item['name'],
                    "quantity": 1,
                    "price": item['paid_price'],
                    "amount": item['paid_price']
                })
            new_order.owner_department = "All Departments"
            new_order.sales_name = "Sales Team"
            new_order.marketplace_platform = "Lazada"
            new_order.insert(ignore_permissions=True)
            frappe.db.commit()
            return new_order.name
        

    def check_product_sku(self, order_info):
        for item in order_info:
            sku = item.get('sku')
            exists = frappe.db.exists("Item", sku, cache=False)
            if not exists:
                return 0
            else:
                return 1

    def inser_customer(self, order_details, buyer_id):
        customer_info = order_details['address_shipping'] 
        name = customer_info["first_name"] + customer_info["last_name"]
        try:
            existing_customer = frappe.get_doc("Customer", {"marketplace_buyer_id": buyer_id})
            return existing_customer.name
        except frappe.DoesNotExistError:
            customer = frappe.get_doc({
                "doctype": "Customer",
                "full_name": name,
                "customer_name": name,
                "customer_group": "All Customer Groups",
                "territory": "Thailand",
                "marketplace_buyer_id": buyer_id
            })
            customer.insert(
                ignore_permissions=True
            )
            frappe.db.commit()
            self.create_contact_for_customer(customer.name, customer_info)
            return customer.name

            
    def create_contact_for_customer(self,customer, customer_info):
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": customer_info["first_name"],
            "last_name": customer_info["last_name"],
            "address_line1": customer_info["address1"],
            "address_type": "Shipping",
            "customer": customer,
            "is_primary_contact": True
        })
        contact.append('links', {
                'link_doctype': 'Customer',
                'link_name': customer
        })
        contact.append('phone_nos', {
                'phone':  customer_info["phone"],
        })
        contact.insert(ignore_permissions=True)
        frappe.db.commit()
        return contact

    
    def getorderdetails_addional_expenss( self, ordersn):
        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_password('lazada_access_token')
        if accesstoken:
            olddate = datetime.now() - timedelta(days=4*30)
            olddate_str = olddate.strftime("%Y-%m-%d")
            client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
            request = LazopRequest('/finance/transaction/details/get','GET')
            request.add_api_param('start_time', olddate_str)
            request.add_api_param('end_time', datetime.now().strftime("%Y-%m-%d"))
            request.add_api_param('trade_order_id', ordersn)
            order_details = client.execute(request, accesstoken).body
            return order_details["data"]
        
        
        
    def get_order_info( self, ordersn):
        docSettings = frappe.get_single("Marketplace integration")
        accesstoken = docSettings.get_password('lazada_access_token')
        order_data = {}
        if accesstoken:
            client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
            request = LazopRequest('/order/get','GET')
            request.add_api_param('order_id', ordersn)
            order_details = client.execute(request, accesstoken).body


            if order_details:
                order_details = json.dumps(order_details)
                client = LazopClient('https://api.lazada.co.th/rest','112284','eRIs543RcqFoE9GXHA1BLEzOYUHDZJy0')
                request = LazopRequest('/order/items/get','GET')
                request.add_api_param('order_id', ordersn)
                response_items = client.execute(request, accesstoken).body
                response_items = json.dumps(response_items)
                order_data['order_details'] = order_details
                order_data['order_items'] = response_items

            return order_data



    



    
    
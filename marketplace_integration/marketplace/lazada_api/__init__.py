import frappe
import json

from marketplace_integration.lazada import LazopClient, LazopRequest
from marketplace_integration.image import compress_image



def extract_response(response):
    if not response.type:
        return response.body
    raise Exception(response.body)

class LazadaClient:
    def __init__(self, url):
        app_manager = frappe.get_doc("Marketplace Management")
        app_key = app_manager.client_id
        app_secret = app_manager.client_secret
    
        self.client = LazopClient(url, app_key, app_secret)
        marketplace_integration = frappe.get_single("Marketplace integration")
        # self.access_token = marketplace_integration.get_password("lazada_access_token")
        self.access_token = "50000700424ySYdbrMjTBjmPvRqaZ2fvjhwZ1552d452UuebihPgNyzkH6oX2AWw"

    def execute(self, request):
        return self.client.execute(request, self.access_token)

    # Product APIs
    def get_product(self, item_id):
        request = LazopRequest("/product/item/get", "GET")
        request.add_api_param("item_id", item_id)
        response = self.execute(request)

        return extract_response(response)

    def get_products(self, criteria, limit=10):
        request = LazopRequest("/products/get", "GET")

        for key, value in criteria.items():
            quest.add_api_param(key, value)
        request.add_api_param("limit", limit)

        response = self.execute(request)

        return extract_response(response)

    def update_product(self, product_data):
        payload = {
            "Request": {
                "Product": {
                    "ItemId": product_data.get("item_ID"),
                    "Attributes": product_data.get("attributes"),
                    "Skus": {
                        "Sku": product_data.get("skus")
                    }
                }
            }
        }

        request = LazopRequest("/product/update", "POST")
        request.add_api_param("payload", json.dumps(payload))

        response = self.execute(request)
        return extract_response(response)

    def remove_product(self, seller_sku_list):
        request = LazopRequest("/product/remove", "POST")
        request.add_api_param("seller_sku_list", json.dumps(seller_sku_list))

        response = self.execute(request)
        return extract_response(response)

    def create_product(self, product_info):
        payload = {
            "Request": {
                "Product": {
                    **product_info.get("Product"),
                    "Attributes": product_info.get("Attributes"),
                    "Skus": {
                        "Sku": product_info.get("Skus")
                    }
                },
            }
        }

        request = LazopRequest("/product/create", "POST")
        request.add_api_param("payload", json.dumps(payload))
        
        response = self.execute(request)
        return extract_response(response)

    def adjust_sellable_quantity(self, item_id, sku_id, seller_sku, sellable_qty, warehouses_info=None):
            
        request_payload = {
            "Request": {
                "Product": {
                    "Skus":{
                        "Sku": {
                            "ItemId": item_id,
                            "SkuId": sku_id,
                            "SellerSku": seller_sku
                        }
                    }
                }
            }
        }

        multi_warehouse_info = []
        if warehouses_info:
            for name, value in warehouse.items():
                multi_warehouse_info["WerehouseCode"] = name,
                multi_warehouse_info["SellableQuantity"] = str(value)
        if multi_warehouse_info:
            request_payload["Request"]["Product"]["Skus"]["Sku"]["MultiWarehouseInventory"] = multi_warehouse_info
        else:
            request_payload["Request"]["Product"]["Skus"]["Sku"]["SellableQuantity"] = str(sellable_qty)

        request = LazopRequest("/product/stock/sellable/adjust", "POST")
        print(json.dumps(request_payload))
        request.add_api_param("payload", json.dumps(request_payload))
        
        response = self.execute(request)
        return extract_response(response)

    def deactivate_product(self, item_id):
        request_payload = {
            "Request": {
                "Product": {
                    "ItemId": item_id
                }
            }
        }

        request = LazopRequest("/product/deactivate", "POST")
        request.add_api_param("apiRequestBody", json.dumps(request_payload))
        
        response = self.execute(request)
        return extract_response(response)

    def get_category_tree(self):
        request = LazopRequest("/category/tree/get", "GET")
        request.add_api_param('language_code', 'en_US')
        
        response = self.execute(request)
        return extract_response(response)

    def get_category_attributes(self, category_id):
        request = LazopRequest("/category/attributes/get", "GET")
        request.add_api_param("primary_category_id", category_id)
        request.add_api_param("language_code", "en_US")

        response = self.execute(request)
        return extract_response(response)

    def get_category_suggestion(self, title):
        request = LazopRequest("/product/category/suggestion/get", "GET")
        request.add_api_param("product_name", title)
        response = self.execute(request)

        return extract_response(response)
    
    def get_brands(self, start_from = 0, page_size = 20):
        request = LazopRequest("/category/brands/query", "GET")
        request.add_api_param("startRow", start_from)
        request.add_api_param("pageSize", page_size)
        response = self.execute(request)
        return extract_response(response)

    def upload_image(self, image_path):
        compressed_image = compress_image(image_path, 1)
        
        request = LazopRequest("/image/upload", "POST")
        request.add_file_param("image", compressed_image)
        response = self.execute(request)

        return extract_response(response)

    # Get a list of Skus along with Images, Remember images should be uploaded to 
    # Example:
    # [{"sku_id": 1234, "images": ["url1", "url2"]}]
    def set_images(self, skus_data):
        sku_img_payload = list()
        for sku in skus_data:
            processed_sku = {
                "SkuId": sku.get("sku_id"),
                "Images": {
                    "Image": sku.get("images")
                }
            }
            sku_image_payload.append(processed_sku)

        payload = {
            "Request": {
                "Product":{
                    "Skus": {
                        "Sku": sku_img_payload
                        }
                    }
                }
            }
        request = LazopRequest("/images/set", "POST")
        request.set_api_param("payload", json.dumps(payload))

        response = self.execute(request)
        return extract_response(response)

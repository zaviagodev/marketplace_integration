from marketplace_integration.marketplace.lazada_api import LazadaClient
from datetime import datetime

class LazadaSourceManager:
    def __init__(self):
        self.client = LazadaClient("https://api.lazada.co.th/rest")
        self.products = self._fetch_products()

    # If seller_id is none fetch from all the shops by default
    def _fetch_products(self, seller_id = None):
        processed_data = {}
        offset = 0
        while True:
            result = self.client.get_products({}, 20, offset).get("data")
            products = result.get("products", None)
            if not products:
                break
            offset += len(products)

            for item in products:
                item_attributes = item.get("attributes")
                product_name = item_attributes.get("name")
                try:
                    product = {
                        "created_at": datetime.fromtimestamp(int(item.get("created_time"))/1000),
                        "updated_at": datetime.fromtimestamp(int(item.get("updated_time"))/1000),
                        "images": item.get("images")[0],
                        "description": item_attributes.get("description"),
                        "name": product_name,
                        "skus": item.get("skus"),
                        "status": item.get("status"),
                        "product_name": product_name
                    }
                    processed_data[product_name] = product
                except Exception as e:
                    print(e)

        return processed_data

    def get_product_skus(self, name):
        return self.products.get(name).get('skus')

    def get_product(self, name):
        return self.products.get(name)

    def get_list(self, filters = None):
        return self.products

    def get_count(self):
        return len(self.products)

lazada_manager = LazadaSourceManager()

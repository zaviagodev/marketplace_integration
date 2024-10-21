// Copyright (c) 2024, zaviago and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lazada Items", {
	refresh: function(frm) {
        frm.clear_table("skus");
        frappe.call({
            method: "marketplace_integration.api.get_product_skus",
            args: {
                "product_name": frm.doc.name
            },
            callback : function(r) {
                if(r.message) {
                
                    r.message.forEach(function(row) {
                        var child_row = frm.add_child("skus");
                        child_row.seller_sku = row.SellerSku;
                        child_row.shop_sku = row.ShopSku;
                        child_row.quantity = row.quantity;
                        child_row.price = row.price;
                        child_row.status = row.Status;
                        child_row.product_weight = row.product_weight;
                        child_row.package_weight = row.package_weight;
                        child_row.package_width = row.package_width;
                        child_row.package_height = row.package_height;
                        child_row.package_length = row.package_length;
                    }); 
                }
                frm.refresh_field("skus")
            }
    })
	},
});

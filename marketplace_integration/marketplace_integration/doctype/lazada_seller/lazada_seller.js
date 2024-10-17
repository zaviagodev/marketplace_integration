// Copyright (c) 2024, zaviago and contributors
// For license information, please see license.txt


function connect_lazada(frm) {
    var site = frappe.urllib.get_base_url();
    var callback_url = frappe.db.get_single_value('Lazada Callback', 'callback')
        .then(value => value);
    var requestData = {
        "client_site": site
    };
    $.ajax({
        type: "GET",
        url: callback_url,
        contentType: "application/json",
        data: requestData,
        success: function (response) {
            if (response && response.message.url) {
                window.open(response.message.url, "_self");
            }
        },
        error: function (xhr, status, error) {
            console.log(xhr);
            frappe.msgprint("Error: " + error + status + xhr);
        }
    });
}
frappe.ui.form.on("Lazada Seller", {
    onload: function (lazada_seller_form) {
        if (lazada_seller_form.is_new()) {
            lazada_seller_form.toggle_display("method", true);
            lazada_seller_form.toggle_display("refresh_token_btn", false);
        } else {
            lazada_seller_form.toggle_display("method", false);
            lazada_seller_form.toggle_display("refresh_token_btn", true);

        }
    },
    connect_lazada: connect_lazada,
    refresh_token_btn: connect_lazada
});

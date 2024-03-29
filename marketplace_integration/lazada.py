# -*- coding: utf-8 -*-
'''
Created on 2018-03-21

@author: xuteng.xt
'''

import requests
import time
import hmac
import hashlib
import json
import mimetypes
import itertools
import random
import logging
import os
from os.path import expanduser
import socket
import platform
from requests import Request, Session, exceptions


# dir = os.getenv('HOME')
dir = expanduser("~")
isExists = os.path.exists(dir + "/logs")
if not isExists:
    os.makedirs(dir + "/logs") 
logger = logging.getLogger(__name__)
logger.setLevel(level = logging.ERROR)
handler = logging.FileHandler(dir + "/logs/lazopsdk.log." + time.strftime("%Y-%m-%d", time.localtime()))
handler.setLevel(logging.ERROR)
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

P_SDK_VERSION = "lazop-sdk-python-20181207"

P_APPKEY = "app_key"
P_ACCESS_TOKEN = "access_token"
P_TIMESTAMP = "timestamp"
P_SIGN = "sign"
P_SIGN_METHOD = "sign_method"
P_PARTNER_ID = "partner_id"
P_DEBUG = "debug"

P_CODE = 'code'
P_TYPE = 'type'
P_MESSAGE = 'message'
P_REQUEST_ID = 'request_id'

P_API_GATEWAY_URL_SG = 'https://api.lazada.sg/rest'
P_API_GATEWAY_URL_MY = 'https://api.lazada.com.my/rest'
P_API_GATEWAY_URL_VN = 'https://api.lazada.vn/rest'
P_API_GATEWAY_URL_TH = 'https://api.lazada.co.th/rest'
P_API_GATEWAY_URL_PH = 'https://api.lazada.com.ph/rest'
P_API_GATEWAY_URL_ID = 'https://api.lazada.co.id/rest'
P_API_AUTHORIZATION_URL = 'https://auth.lazada.com/rest'

P_LOG_LEVEL_DEBUG = "DEBUG"
P_LOG_LEVEL_INFO = "INFO"
P_LOG_LEVEL_ERROR = "ERROR"


def sign(secret,api, parameters):
    #===========================================================================
    # @param secret
    # @param parameters
    #===========================================================================
    sort_dict = sorted(parameters)
    
    parameters_str = "%s%s" % (api,
        str().join('%s%s' % (key, parameters[key]) for key in sort_dict))

    h = hmac.new(secret.encode(encoding="utf-8"), parameters_str.encode(encoding="utf-8"), digestmod=hashlib.sha256)

    return h.hexdigest().upper()


def mixStr(pstr):
    if(isinstance(pstr, str)):
        return pstr
    elif(isinstance(pstr, unicode)):
        return pstr.encode('utf-8')
    else:
        return str(pstr)

def logApiError(appkey, sdkVersion, requestUrl, code, message):
    localIp = socket.gethostbyname(socket.gethostname())
    platformType = platform.platform()
    logger.error("%s^_^%s^_^%s^_^%s^_^%s^_^%s^_^%s^_^%s" % (
        appkey, sdkVersion,
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        localIp, platformType, requestUrl, code, message))

class LazopRequest(object):
    def __init__(self,api_pame,http_method = 'POST'):
        self._api_params = {}
        self._file_params = {}
        self._api_pame = api_pame
        self._http_method = http_method

    def add_api_param(self,key,value):
        self._api_params[key] = value

    def add_file_param(self,key,value):
        self._file_params[key] = value


class LazopResponse(object):
    def __init__(self):
        self.type = None
        self.code = None
        self.message = None
        self.request_id = None
        self.body = None
    
    def __str__(self, *args, **kwargs):
        sb = "type=" + mixStr(self.type) +\
            " code=" + mixStr(self.code) +\
            " message=" + mixStr(self.message) +\
            " requestId=" + mixStr(self.request_id)
        return sb

class LazopClient(object):
    
    log_level = P_LOG_LEVEL_ERROR
    def __init__(self, server_url,app_key,app_secret,timeout=30):
        self._server_url = server_url
        self._app_key = app_key
        self._app_secret = app_secret
        self._timeout = timeout
    
    def execute(self, request,access_token = None):

        sys_parameters = {
            P_APPKEY: self._app_key,
            P_SIGN_METHOD: "sha256",
            P_TIMESTAMP: str(int(round(time.time()))) + '000',
            P_PARTNER_ID: P_SDK_VERSION
        }

        if(self.log_level == P_LOG_LEVEL_DEBUG):
            sys_parameters[P_DEBUG] = 'true'

        if(access_token):
            sys_parameters[P_ACCESS_TOKEN] = access_token

        application_parameter = request._api_params;

        sign_parameter = sys_parameters.copy()
        sign_parameter.update(application_parameter)

        sign_parameter[P_SIGN] = sign(self._app_secret,request._api_pame,sign_parameter)

        api_url = "%s%s" % (self._server_url,request._api_pame)

        full_url = api_url + "?";
        for key in sign_parameter:
            full_url += key + "=" + str(sign_parameter[key]) + "&";
        full_url = full_url[0:-1]

        try:
            if(request._http_method == 'POST' or len(request._file_params) != 0) :
                r = requests.post(api_url,sign_parameter,files=request._file_params, timeout=self._timeout)
            else:
                r = requests.get(api_url,sign_parameter, timeout=self._timeout)
        except Exception as err:
            logApiError(self._app_key, P_SDK_VERSION, full_url, "HTTP_ERROR", str(err))
            raise err

        response = LazopResponse()

        jsonobj = r.json()

        if P_CODE in jsonobj:
            response.code = jsonobj[P_CODE]
        if P_TYPE in jsonobj:
            response.type = jsonobj[P_TYPE]
        if P_MESSAGE in jsonobj:
            response.message = jsonobj[P_MESSAGE]
        if P_REQUEST_ID in jsonobj:
            response.request_id = jsonobj[P_REQUEST_ID]

        if response.code is not None and response.code != "0":
            logApiError(self._app_key, P_SDK_VERSION, full_url, response.code, response.message)
        else:
            if(self.log_level == P_LOG_LEVEL_DEBUG or self.log_level == P_LOG_LEVEL_INFO):
                logApiError(self._app_key, P_SDK_VERSION, full_url, "", "")

        response.body = jsonobj

        return response
    


class Client(object):

    BASE_URL = "https://partner.shopeemobile.com"
    BASE_TEST_URL = "https://partner.test-stable.shopeemobile.com"
    BASE_API_URL = "/api/v2/"


    def __init__(self, shop_id, partner_id, partner_key, redirect_url, test_env=False, code = None ,access_token = None, refresh_token = None):
        ''' initialize basic params and cache class
        '''
        if test_env:
            self.BASE_URL = self.BASE_TEST_URL
        self.partner_id = int(partner_id)
        self.partner_key = partner_key
        self.redirect_url = redirect_url
        self.host = self.BASE_URL
        self.shop_id = int(shop_id)
        self.code = code
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.timeout = None

        self.CACHED_MODULE = {}

    def __getattr__(self, name):
        try:
            value = super(Client, self).__getattribute__(name)
        except AttributeError as e:
            value = self._get_cached_module(name)
            if not value:
                raise e
        return value

    def _make_timestamp(self):
        return int(time.time())

    def set_access_token(self, access_token):
        self.access_token = access_token

#    def set_additional_parameter(self, parameter, timest, access_token, sign):
#        add_param = {
#            "Sign" : sign,
#            "Timestamp" : timest,
#            "access_token" : access_token
#        }
#        parameter.update(add_param)
#        return parameter
    def _make_default_parameter(self, timest, sign):
        return {
            "Partner_id": self.partner_id,
            "Timestamp": timest,
            "Access_token": self.access_token,
            "Shop_id": self.shop_id,
            "Sign": sign
        }

    def _make_short_default_parameter(self, timest, sign):
        return {
            "Partner_id": self.partner_id,
            "Sign": sign,
            "Timestamp": timest
        }

    def _api_sign(self, path, timest):
        base_string = f'{self.partner_id}{path}{timest}{self.access_token}{self.shop_id}'.encode()
        sign = hmac.new(self.partner_key.encode(), base_string, hashlib.sha256).hexdigest()
        return sign

    def _api_short_sign(self, path, timest):
        base_string = f'{self.partner_id}{path}{timest}'.encode()
        sign = hmac.new(self.partner_key.encode(), base_string, hashlib.sha256).hexdigest()
        return sign

    def _api_url(self, path):
        url = self.host + path
        return  url

    def _create_parameter_url(self, url, parameter):
        if parameter !=None:
            url = url + "?"
            par = ""
            for param in parameter:
                if par != "":
                    par = par + "&"
                par = par + f"{param.lower()}={parameter[param]}"
            return url + par
        return url

    def _build_request(self, uri, method, body):
        method = method.upper()
        headers = {'Content-Type': 'application/json'}
        timest = self._make_timestamp()
        uri = self.BASE_API_URL + uri
        url = self.host + uri
        if ("/public/" in uri) or ("/push/" in uri):
            sign = self._api_short_sign(uri, timest)
            parameter = self._make_short_default_parameter(timest, sign)
        else:
            sign = self._api_sign(uri, timest)
            parameter = self._make_default_parameter(timest, sign)
#        parameter = self.set_additional_parameter(parameter, sign, timest, self.access_token)
        req = Request(method, url, headers=headers)
        if body:
            if method in ["POST", "PUT", "PATH"]:
                req.json = body
            else:
                parameter.update(body)
        req.url = self._create_parameter_url(url, parameter)
        return req

    def _build_response(self, resp):
        '''Decoding JSON - Decode json string to python object
        JSONDecodeError can happen when requests have an HTTP error code like 404 and try to parse the response as JSON
        '''
        if resp.status_code / 100 == 2:
            body = json.loads(resp.text)
        else:
            body = {"request_id": None, "error": resp.status_code, "msg": "http error code"}

        return body

        # if "error" not in body:
        #     return body
        # else:
        #     raise AttributeError(body["error"])

    def _get_cached_module(self, key):
        CACHED_MODULE = self.CACHED_MODULE.get(key)

        if not CACHED_MODULE:
            installed = self.registered_module.get(key)
            if not installed:
                return None
            CACHED_MODULE = installed(self)
            self.CACHED_MODULE.setdefault(key, CACHED_MODULE)
        return CACHED_MODULE

    def execute(self, uri, method, body=None):
        ''' defalut timeout value will be 10 seconds
        '''
        #parameter = self._make_default_parameter()
        if body.get("timeout"):
            timeout = body.get("timeout")
            body.pop("timeout")
        else:
            timeout = 10

        #if body is not None:
            #parameter.update(body)

        req = self._build_request(uri, method, body)
        print(req.params)
        print(req.url)
        prepped = req.prepare()

        s = Session()
        resp = s.send(prepped, timeout=timeout)
        resp = self._build_response(resp)
        return resp

    def _sign(self, path, timest):
        base_string = f'{self.partner_id}{path}{timest}'.encode()
        sign = hmac.new(self.partner_key.encode(), base_string, hashlib.sha256).hexdigest()
        return sign

    def auth_url(self, path):
        timest = self._make_timestamp()

        #base_string = f'{self.partner_id}{path}{timest}'.encode()
        #sign = hmac.new(self.partner_key.encode(), base_string, hashlib.sha256).hexdigest()

        sign = self._sign(path, timest)
        url = self.host + path + f'?partner_id={self.partner_id}&timestamp={timest}&sign={sign}'
        return sign, url

    def shop_authorization(self, redirect_url):
        '''
            The difference between hmac and hashlib,
            hmac uses the provided key to generate a salt and make the hash more strong, while hashlib only hashes the provided message

            In shopee partner API, shopee use hmac for general encryption while using hashlib for Authorize and CancelAuthorize module
        '''

        path = "/api/v2/shop/auth_partner"
        url = self.auth_url(path)[1] + f'&redirect={redirect_url}'
        return url

    def get_code(self):
        url = self.shop_authorization(self.redirect_url)
        browser = webdriver.Chrome('c:\\chromedriver\\chromedriver.exe')
        browser.get(url)
        while self.redirect_url not in browser.current_url:
            pass
        code = parse_url(browser.current_url).query.split('&')
        browser.close()
        self.code = code[0] = code[0].replace('code=', '')
        self.shop_id = int(code[1].replace('shop_id=', ''))
        return self.code, self.shop_id

    def get_token(self):
        body = {'code': self.code, 'shop_id': int(self.shop_id), 'partner_id': int(self.partner_id)}
        url = self.auth_url('/api/v2/auth/token/get')[1]
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, json=body, headers=headers).json()
        print(resp)
        self.access_token = resp['access_token']
        self.refresh_token = resp['refresh_token']
        self.timeout = resp['expire_in']
        return self.access_token, self.timeout, self.refresh_token

    def get_access_token(self, shop_id, partner_id, partner_key, refresh_token):
        body = {'shop_id': int(shop_id), 'partner_id': int(partner_id), 'refresh_token': refresh_token}
        url = self.auth_url('/api/v2/auth/access_token/get')[1]
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, json=body, headers=headers).json()
        print(resp)
        self.access_token = resp['access_token']
        self.refresh_token = resp['refresh_token']
        self.timeout = resp['expire_in']
        return self.access_token, self.timeout, self.refresh_token
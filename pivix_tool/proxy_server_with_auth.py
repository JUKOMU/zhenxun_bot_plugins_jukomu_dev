import requests
from flask import Flask, request, jsonify, Response
from flask_compress import Compress

# --- 配置 ---
SECRET_TOKEN = "xxx"
SERVER_PORT = 0000

# 初始化 Flask 应用
app = Flask(__name__)
Compress(app)


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def proxy_request(path):
    auth_token = request.headers.get('Authorization')
    if not auth_token:
        return ('', 401)

    if auth_token != SECRET_TOKEN:
        return ('', 403)

    return_type = request.args.get('return_as', 'json').lower()

    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "'url' parameter is required"}), 400

    method = request.method
    params = request.args.to_dict()
    params.pop('url', None)
    params.pop('return_as', None)

    headers = {key: value for key, value in request.headers if key.lower() not in ['host', 'authorization']}

    cookies = request.cookies
    data = request.get_data()
    json_data = request.get_json(silent=True)

    try:
        resp = requests.request(
            method=method,
            url=target_url,
            params=params,
            headers=headers,
            cookies=cookies,
            data=data,
            json=json_data,
            allow_redirects=True
        )

        if return_type == 'binary':
            # 直接返回原始二进制数据和目标服务器的 Content-Type
            content_type = resp.headers.get('Content-Type', 'application/octet-stream')
            return Response(resp.content, mimetype=content_type, status=resp.status_code)

        else:
            try:
                response_body = resp.json()
            except ValueError:
                response_body = {'raw_content': resp.text}

            response_to_caller = {
                'status_code': resp.status_code,
                'headers': dict(resp.headers),
                'body': response_body
            }
            return jsonify(response_to_caller)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Failed to reach target server", "details": str(e)}), 502
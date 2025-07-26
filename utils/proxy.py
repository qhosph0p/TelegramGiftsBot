def get_userbot_proxy(db_proxy):
    proxy_url = f"socks5://{db_proxy.get('username')}:{db_proxy.get('password')}@{db_proxy.get('hostname')}:{db_proxy.get('port')}"
    return {
        "proxy_type": "socks5",
        "addr": db_proxy.get("hostname"),
        "port": int(db_proxy.get("port")),
        "username": db_proxy.get("username"),
        "password": db_proxy.get("password"),
        "url": proxy_url
    }

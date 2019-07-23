from flask import render_template

from . import index_blu


# 测试
@index_blu.route('/')
def index():
    return render_template('news/index.html')
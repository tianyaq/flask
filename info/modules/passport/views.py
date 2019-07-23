import re
import random
from datetime import datetime

from flask import request, current_app, abort, make_response, jsonify, session
from info import redis_store, constants, db
from info.models import User
from info.response_code import RET
from info.utils.yuntongxun import sms
from . import passport_blu
from info.utils.captcha.captcha import captcha


@passport_blu.route('/image_code')
def get_image_code():
    '''
    生成图片验证码
    :return:
    '''
    # 1. 获取参数
    image_code_id = request.args.get('image_Code')

    # 2. 校验参数
    if not image_code_id:
        abort(403)

    # 3. 生成图片验证码
    name, text, image = captcha.generate_captcha()

    # 4. 保存图片验证码
    try:
        redis_store.setex('image_code_' + image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)
    except Exception as e:
        current_app.logger.error(e)
    response = make_response(image)
    print(text)
    # 5.返回图片验证码
    response.headers['Content-Type'] = 'image/png'
    return response


@passport_blu.route('/sms_code', methods=["POST"])
def send_sms_code():
    """
    发送短信的逻辑
    :return:
    """
    # 1.将前端参数转为字典
    # sms_code_id = request.json.get('sms_code_id')
    mobile = request.json.get('mobile')
    image_code = request.json.get('image_code')
    image_code_id = request.json.get('image_code_id')
    # 2. 校验参数(参数是否符合规则，判断是否有值)
    print(mobile, image_code_id, image_code)
    if not all([mobile, image_code, image_code_id]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不全')
    # 判断参数是否有值
    if not re.match('1[356789]\d{9}', mobile):
        return jsonify(errno=RET.DATAERR, errmsg='手机号格式错误')
    # 3. 先从redis中取出真实的验证码内容
    try:
        real_image_code = redis_store.get('image_code_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询图片验证码失败')
    if not real_image_code:
        return jsonify(errno=RET.PARAMERR, errmsg='图片验证码过期')
    try:
        redis_store.delete('ImageCode_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
    if real_image_code.lower() != image_code.lower():
        return jsonify(errno=RET.DATAERR, errmsg='图片验证码错误')
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg='查询数据库异常')
    else:
        # 判断查询结果
        if user:
            return jsonify(errno=4004, errmsg='手机号已注册')
    # 4. 与用户的验证码内容进行对比，如果对比不一致，那么返回验证码输入错误
    # 5. 如果一致，生成短信验证码的内容(随机数据)
    sms_code = random.randint(000000, 999999)
    # 6. 发送短信验证码
    # try:
    #     ccp = sms.CCP()
    # #
    # #     # 调用云通讯的模板方法发送短信
    #     result = ccp.send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES / 60], 1)
    # except Exception as e:
    #     current_app.logger.error(e)
    #     return jsonify(errno=4004, errmsg='发送短信异常')
    print(sms_code)

    # 保存验证码内容到redis
    try:
        redis_store.setex('SMSCode_' + mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=4004, errmsg='保存短信验证码失败')
    # 7. 告知发送结果
    # print(result)
    #
    # if 0 == result:
    #     return jsonify(errno=RET.OK, errmsg='发送成功')
    # else:
    #     return jsonify(errno=RET.DATAERR, errmsg='发送失败')
    return jsonify(errno=RET.OK, errmsg='ok')


@passport_blu.route('/register', methods=["POST"])
def register():
    """
    注册功能
    :return:
    """

    # 1. 获取参数和判断是否有值
    mobile = request.json.get('mobile')
    password = request.json.get('password')
    smscode = request.json.get('smscode')
    print(mobile, smscode, password)
    if not all([mobile, password, smscode]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不全')

    if not re.match(r"1[35678]\d{9}$", mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机号有误')

    # 2. 从redis中获取指定手机号对应的短信验证码的
    try:
        real_sms_code = redis_store.get('SMSCode_' + mobile)
    except BaseException as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='数据有误1')
    # 3. 校验验证码
    if smscode != real_sms_code:
        return jsonify(errno=RET.PARAMERR, errmsg='验证码有误')

    # 4. 初始化 user 模型，并设置数据并添加到数据库
    try:
        user = User()
        user.mobile = mobile
        user.password_hash = password
        user.nick_name = mobile
        user.last_login = datetime.now()

        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='数据有误2')
    # 5. 保存用户登录状态
    session['use_id'] = user.id
    session['mobile'] = user.mobile
    session['nick_name'] = mobile

    # 6. 返回注册结果
    print('---------')
    return jsonify(errno=RET.OK, errmsg='注册成功')


@passport_blu.route('/login', methods=["POST"])
def login():
    """
    登陆功能
    :return:
    """

    # 1. 获取参数和判断是否有值
    mobile = request.json.get("mobile")
    password = request.json.get("password")
    print(mobile)
    print(password)
    if not all([mobile, password]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不全')
    # 2. 从数据库查询出指定的用户
    user = User.query.filter(mobile == mobile).first()

    # 3. 校验密码
    if not user:
        return jsonify(errno=RET.NODATA, errmsg="账号不存在")
    if not user.check_password(password):
        return jsonify(errno=RET.PWDERR, errmsg="密码错误")

    # 4. 保存用户登录状态
    session['user_id'] = user.id
    session['user_name'] = user.nick_name
    session['user_mobile'] = user.mobile
    #
    # 5. 登录成功返回
    return jsonify(errno=RET.OK, errmsg="登陆成功")

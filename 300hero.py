from json import load, dump
import time
import re
from aiohttp.client_exceptions import ServerDisconnectedError
from copy import deepcopy
from asyncio import Lock
from os.path import dirname, join, exists

from hoshino import Service,priv
from hoshino.util import FreqLimiter
from urllib.parse import quote
from nonebot import get_bot
from aiohttp import ClientSession
import nest_asyncio
nest_asyncio.apply()

sv_help = '''
【出租推送功能指令】
-[绑定角色XXX|大区名]  绑定角色ID和所在大区，角色名和大区用|分开写
-[查询角色/角色查询]  查询指定ID是否存在或者绑定在谁那
-[启用/停止自动推送]  开启或关闭出租信息自动推送
-[删除角色绑定]  删除掉自己的角色绑定信息
-[角色绑定状态]  查询自己的角色绑定信息
-[查胜场]  查询自己绑定角色的胜场信息，用@可以查询他人的信息
-[查出租]  查询自己绑定角色的出租信息，用@可以查询他人的信息 m.tb.cn
'''.strip()

sv = Service(
    name = '300英雄出租',  #功能名
    use_priv = priv.NORMAL, #使用权限   
    manage_priv = priv.ADMIN, #管理权限
    visible = True, #是否可见
    enable_on_default = True, #是否默认启用
    bundle = '娱乐', #属于哪一类
    help_ = sv_help #帮助文本
    )
    
@sv.on_fullmatch(["出租帮助"])
async def bangzhu(bot, ev):
    await bot.send(ev, sv_help)

lmt = FreqLimiter(5)    
curpath = dirname(__file__)
config = join(curpath, 'gid_pool.json')
root = {
    'arena_bind' : {}
}
lck = Lock()
if exists(config):
    with open(config,encoding='UTF-8') as fp:
        root = load(fp)
binds = root['arena_bind']

def save_binds():
    with open(config,'w',encoding='UTF-8') as fp:
        dump(root,fp,indent=4,ensure_ascii=False)

async def getjson(url):
    async with ClientSession() as session:
        async with session.get(url) as response:
            response = await response.json(content_type=None)
            return response

@sv.on_prefix(('绑定角色'))
async def bangqu(bot, ev):
    global binds, lck,cache
    async with lck:
        uid = str(ev['user_id'])
        user=ev.message.extract_plain_text()
        last = binds[uid] if uid in binds else {}
        binds[uid] = {
            'id': user,
            'gid': str(ev['group_id']),
            'push_on': last.get('push_on',False),
            'state':'0',#出租状态
            'win':'0'
        }
        save_binds()
    await bot.finish(ev, f'\n角色：{user}\n绑定成功！', at_sender=True)
    

@sv.on_rex('(启用|停止)自动推送')
async def change_arena_sub(bot, ev):
    global binds, lck
    key = 'push_on'
    uid = str(ev['user_id'])
    async with lck:
        if not uid in binds:
            await bot.send(ev,'您还未绑定角色',at_sender=True)
        else:
            binds[uid][key] = ev['match'].group(1) == '启用'
            save_binds()
            await bot.finish(ev, f'{ev["match"].group(0)}成功', at_sender=True)
            

@sv.on_prefix('删除角色绑定')
async def delete_arena_sub(bot,ev):
    global binds, lck
    uid = str(ev['user_id'])
    if ev.message[0].type == 'at':
        if not priv.check_priv(ev, priv.SUPERUSER):
            await bot.finish(ev, '删除他人绑定请联系维护', at_sender=True)
            return
        uid = str(ev.message[0].data['qq'])
    elif len(ev.message) == 1 and ev.message[0].type == 'text' and not ev.message[0].data['text']:
        uid = str(ev['user_id'])
    if not uid in binds:
        await bot.finish(ev, '未绑定角色', at_sender=True)
        return
    async with lck:
        binds.pop(uid)
        save_binds()
    await bot.finish(ev, '删除角色绑定成功', at_sender=True)
    
    
@sv.on_prefix('角色绑定')
async def send_arena_sub_status(bot,ev):
    global binds, lck
    uid = str(ev['user_id'])
    if ev.message[0].type == 'at':
        id = str(ev.message[0].data['qq'])
        if not id in binds:
            await bot.send(ev,'对方还未绑定角色！', at_sender=True)
        else:
            info = binds[id]
            state=info['state']
            if state=='1':
                msg='出租中'
            elif state=='0':
                msg='待租'
            else:
                msg='下架'
            await bot.finish(ev,f"对方绑定信息：\n角色：{info['id']}\n状态：{msg}\n推送：{'开启' if info['push_on'] else '关闭'}",at_sender=True)
    else:
        if not uid in binds:
            await bot.send(ev,'您还未绑定角色！', at_sender=True)
        else:
            info = binds[uid]
            state=info['state']
            if state=='1':
                msg='出租中'
            elif state=='0':
                msg='待租'
            else:
                msg='下架'
            await bot.finish(ev,f"当前绑定信息：\n角色：{info['id']}\n状态：{msg}\n推送：{'开启' if info['push_on'] else '关闭'}",at_sender=True)

#用户id获取
async def user_get(ev):
    uid = str(ev['user_id'])
    key=ev.message.extract_plain_text()
    try:
        id=binds[uid]["id"]
        if key == "":
            key=binds[uid]["id"]
            return key
        else:
            return key
    except:
        return key

@sv.on_prefix(('查胜场'))
async def shengchang(bot, ev):
    if ev.message[0].type == 'at':
        id = str(ev.message[0].data['qq'])
        try:
            key=binds[id]["id"]
        except:
            msg = "对方未绑定角色，无法查询其信息！"
            await bot.send(ev, msg,at_sender=True)
            return
    else:
        key = await user_get(ev)
        if key == "":
            msg = "未绑定角色，请绑定角色或者指定角色名！"
            await bot.send(ev, msg,at_sender=True)
            return
    try:
        now_time=time.strftime('%Y-%m-%d')
        url='http://300.electricdog.net/300hero/{}'.format(quote(key))
        data=await getjson(url)
        data_1=data["data"]
        zcLastMatchTime=data_1["zcLastMatchTime"]
        mat = re.search(r"(\d{4}-\d{1,2}-\d{1,2})",zcLastMatchTime)
        last_time=mat.group(0)
        if last_time != now_time:
            msg='\n该用户今日未曾进行过战场对局'
        else:
            zcWin=str(data_1["zcWin"])
            msg = f'\n用户名：{key}\n今日胜场：{zcWin}\n最后对局：{zcLastMatchTime}'
    except ServerDisconnectedError as e:
        msg='\n胜场网出现故障，暂时无法使用'
    except Exception as e:
        msg='\n未绑定角色或角色不存在，请使用指令：绑定角色XXX'
    await bot.send(ev, msg,at_sender=True)


@sv.on_prefix(('查出租'))
async def chuzu(bot, ev):
    if ev.message[0].type == 'at':
        id = str(ev.message[0].data['qq'])
        try:
            key=binds[id]["id"]
        except:
            msg = "对方未绑定用户，无法查询其信息！"
            await bot.send(ev, msg,at_sender=True)
            return
    else:
        id = str(ev['user_id'])
        key = await user_get(ev)
        if key == "":
            msg = "未绑定用户，请绑定用户或者指定用户名！"
            await bot.send(ev, msg,at_sender=True)
            return
    url='http://api.300mbdl.cn/%E6%8E%A5%E5%8F%A32/%E7%A7%9F%E5%8F%B7/%E7%A7%9F%E5%8F%B7%E5%A4%A7%E5%8E%85?%E9%A1%B5=1&%E9%A1%B5%E9%95%BF=100&%E5%87%BA%E7%A7%9F%E4%B8%AD=true'
    url1='http://api.300mbdl.cn/%E6%8E%A5%E5%8F%A32/%E7%A7%9F%E5%8F%B7/%E7%A7%9F%E5%8F%B7%E5%A4%A7%E5%8E%85?%E9%A1%B5=1&%E9%A1%B5%E9%95%BF=100&%E5%87%BA%E7%A7%9F%E4%B8%AD=false'
    try:
        now_time=time.strftime('%Y-%m-%d')
        getwin_url='http://300.electricdog.net/300hero/{}'.format(quote(key))
        surl=await getjson(getwin_url)
        surl1=surl["data"]
        zcLastMatchTime=surl1["zcLastMatchTime"]
        mat = re.search(r"(\d{4}-\d{1,2}-\d{1,2})",zcLastMatchTime)
        last_time=mat.group(0)
        if last_time != now_time:
            zcWin='0'
        else:
            zcWin=str(surl1["zcWin"])
        
        true_url=await getjson(url)
        false_url=await getjson(url1)
        true_data=true_url['data']
        false_data=false_url['data']
        for item in true_data:
            if key in item.values():
                if item['F角色名']==key:
                    get_time=item['F订单时间']
                    binds[id]['state']='1'
                    save_binds()
            else:
                for item1 in false_data:
                    if key in item1.values():
                        if item1['F角色名']==key:
                            binds[id]['state']='0'
                            save_binds()
                    else:
                        binds[id]['state']='-1'
                        save_binds()
        state=binds[id]['state']
        if state=='1':
            msg=f'\n用户名:{key}\n目前状态:出租中\n出租时间:{get_time}\n当前胜场:{zcWin}'
        elif state=='-1':
            msg=f'\n用户名:{key}\n目前状态:下架\n当前胜场:{zcWin}'
        else:
            msg=f'\n用户名:{key}\n目前状态:待租\n当前胜场:{zcWin}'
    except Exception as e:
        print(e)
        msg='\n查询出错'
    await bot.finish(ev,msg,at_sender=True)


cache = {}
zhuangtai=''
shijian=''

@sv.scheduled_job('interval', minutes=5)
async def chuzu_schedule():
    global zhuangtai,shijian,cache,binds, lck,daqu
    bot = get_bot()
    bind_cache = {}
    async with lck:
        bind_cache = deepcopy(binds)
    for user in bind_cache:
        info = bind_cache[user]
        key=info['id']
        gid=info['gid']
        push_on=info['push_on']
        last_state=info['state']
        if push_on ==False:
            continue
        else:
            url='http://api.300mbdl.cn/%E6%8E%A5%E5%8F%A32/%E7%A7%9F%E5%8F%B7/%E7%A7%9F%E5%8F%B7%E5%A4%A7%E5%8E%85?%E9%A1%B5=1&%E9%A1%B5%E9%95%BF=100&%E5%87%BA%E7%A7%9F%E4%B8%AD=true'
            url1='http://api.300mbdl.cn/%E6%8E%A5%E5%8F%A32/%E7%A7%9F%E5%8F%B7/%E7%A7%9F%E5%8F%B7%E5%A4%A7%E5%8E%85?%E9%A1%B5=1&%E9%A1%B5%E9%95%BF=100&%E5%87%BA%E7%A7%9F%E4%B8%AD=false'
            try:
                sv.logger.info(f'querying {info["id"]} for {info["uid"]}')
                try:
                    now_time=time.strftime('%Y-%m-%d')
                    getwin_url='http://300.electricdog.net/300hero/{}'.format(quote(key))
                    surl=await getjson(getwin_url)
                    surl1=surl.get("data")
                    zcLastMatchTime=surl1.get("zcLastMatchTime")
                    mat = re.search(r"(\d{4}-\d{1,2}-\d{1,2})",zcLastMatchTime)
                    last_time=mat.group(0)
                    if last_time != now_time:
                        binds[id]['win']='0'
                        save_binds()
                    else:
                        zcWin=str(surl1["zcWin"])
                        binds[id]['win']=zcWin
                        save_binds()
                    
                    true_url=await getjson(url)
                    false_url=await getjson(url1)
                    true_data=true_url['data']
                    false_data=false_url['data']
                    for item in true_data:
                        if key in item.values():
                            if item['F角色名']==key:
                                get_time=item['F订单时间']
                                binds[id]['state']='1'
                                save_binds()
                        else:
                            for item1 in false_data:
                                if key in item1.values():
                                    if item1['F角色名']==key:
                                        binds[id]['state']='0'
                                        save_binds()
                                else:
                                    binds[id]['state']='-1'
                                    save_binds()
                    state=binds[id]['state']
                    zcWin=binds[id]['win']
                    if state=='1':
                        msg=f'\n用户名:{key}\n目前状态:出租中\n出租时间:{get_time}\n当前胜场:{zcWin}'
                    elif state=='-1':
                        msg=f'\n用户名:{key}\n目前状态:下架\n当前胜场:{zcWin}'
                    else:
                        msg=f'\n用户名:{key}\n目前状态:待租\n当前胜场:{zcWin}'
                except Exception as e:
                    print(e)
                    msg='\n查询出错'    
            except Exception as e:
                print(e)
            if last_state!=state:
                await bot.send_group_msg(
                                group_id = int(gid),
                                message = f'[CQ:at,qq={user}]\n{msg}')
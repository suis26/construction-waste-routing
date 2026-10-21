# -*- coding: utf-8 -*-
"""
SRS-Route 核心: 接收约束下的建筑垃圾运输调度

对齐 PPT《建筑垃圾运输优化平台第一版》:
  第 7 页  输入 = 产生点(位置/类别/数量/出料时间) + 处理点(接收类别/余量/营业时段) + 车辆(位置/载重/车厢/可用时间)
           输出 = 处理点与到场时段 + 车辆与装卸顺序 + 异常后重新安排
  第 11 页 多点送一点 / 一点送多点 / 算法决策
  第 12 页 综合成本 = 行驶成本 + 等待成本 + 处置费用 + 违约惩罚
  第 14 页 材质标签参与接收匹配

与通用 VRP 的关键差别: 硬约束里多了"接收条件"。
  材质标签必须落在处理设施的接收目录内, 否则车辆到门口必被拒收。
  视觉置信度不足的订单不进自动调度, 转人工复核。

成本参数与时间参数由 PPT 第 9 页反解:
  车速 60 km/h, 装货 10/3 min/t 时, 原案例复现为
  直接: 120 km / 900 元 / A 到厂 08:50
  集运:  50 km / 350 元 / A 到厂 09:30
"""
import math, itertools
from srs_data import (FIXED_TRIP_COST, COST_PER_KM, WAIT_COST_PER_H, LATE_PENALTY_H,
                      HANDLE_COST_T, CO2_PER_KM, RUN_KMH, LOAD_MIN_T, UNLOAD_MIN_T,
                      MATERIAL_REUSE, PREPROCESS_REQUIRED, CATEGORY_ALLOWED_KIND, dist)

CONF_GATE = 0.75          # 视觉置信度门槛, 低于此值转人工复核

# 材质兼容: 土与泥浆与金属须单独运输, 其余惰性物与轻质物可混装后由场站分选
INERT_LIGHT = {'混凝土砖瓦', '石膏', '木材', '塑料'}


def compatible_materials(mats):
    """判断一批材质能否混装在同一车次。"""
    s = set(mats)
    if not s:
        return True, ''
    if '土与泥浆' in s:
        return (len(s) == 1), '泥浆不得与其他材质混装'
    if '金属' in s:
        return (len(s) == 1), '金属须单独运输以保证计价与防混'
    return True, ''


def feasible_depots(order, depots, conf_gate=CONF_GATE):
    """
    模块 C 接收匹配: 材质标签 + 订单类别 双重过滤。
      第一道 材质必须在该设施接收目录内, 否则到场必被拒收
      第二道 类别必须允许该类设施, 如渣土不得进中转场或资源化厂
      第三道 泥浆必须先入预处理, 不得直进消纳或资源化
    """
    out = []
    kinds = CATEGORY_ALLOWED_KIND.get(order['cat'])
    for dp in depots:
        if order['mat'] not in dp['accepts']:
            continue
        if kinds is not None and dp['kind'] not in kinds:
            continue
        if order['cat'] in PREPROCESS_REQUIRED and dp['kind'] != '泥浆预处理':
            continue
        out.append(dp)
    return out


def schedule_route(depot_id, order_ids, vehicles, depots, omap, vehicle):
    """
    计算一条"多点送一点"车次的完整时间表。
    路线: 车辆起点 -> o1 -> o2 -> ... -> ok -> depot
    返回 dict(km, arrive_depot, waits, late, seq, feasible, reason)
    """
    dp = next(d for d in depots if d['id'] == depot_id)
    start = next((d for d in depots if d['id'] == vehicle['start']), dp)
    t = max(vehicle['avail'], min(omap[o]['ready'] for o in order_ids))
    cur = (start['x'], start['y'])
    km = 0.0
    wait_h = 0.0
    seq = []
    load = 0.0
    vol = 0.0
    for oid in order_ids:
        o = omap[oid]
        d = dist({'x': cur[0], 'y': cur[1]}, o)
        km += d
        t += d / RUN_KMH * 60.0
        if t < o['ready']:
            wait_h += (o['ready'] - t) / 60.0
            t = o['ready']
        if t < dp['open_t'] and oid == order_ids[0]:
            pass
        load += o['tons']
        vol += o['vol']
        t += o['tons'] * LOAD_MIN_T
        seq.append((oid, round(t, 1)))
        cur = (o['x'], o['y'])
    d = dist({'x': cur[0], 'y': cur[1]}, dp)
    km += d
    t += d / RUN_KMH * 60.0
    if t < dp['open_t']:
        wait_h += (dp['open_t'] - t) / 60.0
        t = dp['open_t']
    arrive = t
    # 违约: 以最晚一批货的交付期限衡量
    deadline = min(omap[o]['deadline'] for o in order_ids)
    late_h = max(0.0, (t - deadline) / 60.0)
    ok = (load <= vehicle['cap_t'] + 1e-9) and (vol <= vehicle['cap_m3'] + 1e-9) and (t <= dp['close_t'])
    reason = ''
    if load > vehicle['cap_t'] + 1e-9:
        reason = '超载 %.1ft > %.1ft' % (load, vehicle['cap_t'])
    elif vol > vehicle['cap_m3'] + 1e-9:
        reason = '超容积 %.1fm3 > %.1fm3' % (vol, vehicle['cap_m3'])
    elif t > dp['close_t']:
        reason = '超出场站营业时段'
    return dict(km=km, arrive=arrive, wait_h=wait_h, late_h=late_h, seq=seq,
                load=load, vol=vol, feasible=ok, reason=reason)


def route_cost(depot_id, order_ids, vehicles, depots, omap, vehicle, co2=True):
    """模块 D 成本核算: 行驶 + 等待 + 处置 + 违约。"""
    r = schedule_route(depot_id, order_ids, vehicles, depots, omap, vehicle)
    dp = next(d for d in depots if d['id'] == depot_id)
    tons = sum(omap[o]['tons'] for o in order_ids)
    travel = FIXED_TRIP_COST + COST_PER_KM * r['km']
    wait = WAIT_COST_PER_H * r['wait_h']
    disposal = dp['fee_per_t'] * tons
    late = LATE_PENALTY_H * r['late_h']
    total = travel + wait + disposal + late
    r.update(depot=depot_id, tons=tons, travel=travel, wait=wait,
             disposal=disposal, late=late, total=total,
             co2=CO2_PER_KM * r['km'] if co2 else 0.0)
    return r


def all_direct(orders, depots, vehicles, omap):
    """基线: 每笔订单单独直送, 处理厂取最近可行者。"""
    routes = []
    vlist = list(vehicles)
    for i, o in enumerate(orders):
        cands = feasible_depots(o, depots)
        if not cands:
            routes.append(dict(depot=None, orders=[o['id']], infeasible='无接收设施',
                               total=0.0, km=0.0, tons=o['tons']))
            continue
        best = None
        for dp in cands:
            v = vlist[i % len(vlist)]
            c = route_cost(dp['id'], [o['id']], vehicles, depots, omap, v)
            c['vehicle'] = v['id']
            if best is None or c['total'] < best['total']:
                best = c
        routes.append(best)
    return routes


def merge_saving(a, b, vehicles, depots, omap, vehicle):
    """
    模块 B 集运: 判断两笔订单合并是否划算。
    节约 = 分开两趟成本 - 合并一趟成本(含新增等待与操作)。
    同时检查载重、容积、材质兼容、时间窗、卸货顺序。
    """
    same = set(feasible_depots(omap[a], depots)) & set(feasible_depots(omap[b], depots))
    if not same:
        return None
    ok_mat, why_mat = compatible_materials([omap[a]['mat'], omap[b]['mat']])
    if not ok_mat:
        return None
    solo = route_cost(None, [a], vehicles, depots, omap, vehicle) if False else None
    best = None
    for dp in same:
        ca = route_cost(dp['id'], [a], vehicles, depots, omap, vehicle)
        cb = route_cost(dp['id'], [b], vehicles, depots, omap, vehicle)
        for seq in ([a, b], [b, a]):
            cc = route_cost(dp['id'], seq, vehicles, depots, omap, vehicle)
            if not cc['feasible']:
                continue
            saving = ca['total'] + cb['total'] - cc['total']
            if saving <= 0:
                continue
            extra_handle = HANDLE_COST_T * (omap[a]['tons'] + omap[b]['tons'])
            saving -= extra_handle
            if saving > 0 and (best is None or saving > best['saving']):
                best = dict(saving=saving, depot=dp['id'], seq=seq, cost=cc)
    return best


def consolidate(routes, vehicles, depots, omap):
    """
    模块 B: 按节约值从大到小反复合并, 直到无可合并。
    每条路径用 ids 记录订单顺序, 合并时重算时刻与成本。
    只有当 分开两趟成本 - 合并一趟成本 - 新增操作成本 > 0 时才合并。
    """
    cur = []
    for r in routes:
        if r.get('depot') is None:
            continue
        v = next((x for x in vehicles if x['id'] == r.get('vehicle')), vehicles[0])
        cur.append({'depot': r['depot'], 'vehicle': v['id'],
                    'ids': [oid for oid, _ in r['seq']]})
    changed = True
    while changed:
        changed = False
        best = None
        for i in range(len(cur)):
            for j in range(i + 1, len(cur)):
                a, b = cur[i], cur[j]
                v = next((x for x in vehicles if x['id'] == a['vehicle']), vehicles[0])
                ok_mat, _ = compatible_materials([omap[o]['mat'] for o in a['ids'] + b['ids']])
                if not ok_mat:
                    continue
                sa = {d['id'] for d in feasible_depots(omap[a['ids'][0]], depots)}
                sb = {d['id'] for d in feasible_depots(omap[b['ids'][0]], depots)}
                same_ids = sa & sb
                if not same_ids:
                    continue
                ok_mat, _ = compatible_materials([omap[o]['mat'] for o in a['ids'] + b['ids']])
                if not ok_mat:
                    continue
                for dp in [d for d in depots if d['id'] in same_ids]:
                    for seq in (a['ids'] + b['ids'], b['ids'] + a['ids']):
                        cc = route_cost(dp['id'], seq, vehicles, depots, omap, v)
                        if not cc['feasible']:
                            continue
                        solo = 0.0
                        for r0 in (a, b):
                            c0 = route_cost(r0['depot'], r0['ids'], vehicles, depots, omap, v)
                            solo += c0['total'] if c0['feasible'] else 1e18
                        saving = solo - cc['total'] - HANDLE_COST_T * sum(omap[o]['tons'] for o in seq)
                        if saving > 0 and (best is None or saving > best[0]):
                            best = (saving, i, j, dp['id'], seq, v['id'])
        if best:
            _, i, j, did, seq, vid = best
            del cur[max(i, j)]
            del cur[min(i, j)]
            cur.append({'depot': did, 'vehicle': vid, 'ids': seq})
            changed = True

    out = []
    for r in cur:
        v = next((x for x in vehicles if x['id'] == r['vehicle']), vehicles[0])
        c = route_cost(r['depot'], r['ids'], vehicles, depots, omap, v)
        c['vehicle'] = r['vehicle']
        out.append(c)
    return out


def total_metrics(routes):
    ok = [r for r in routes if r.get('depot') is not None]
    return dict(
        cost=sum(r['total'] for r in ok),
        km=sum(r['km'] for r in ok),
        co2=sum(r.get('co2', 0.0) for r in ok),
        travel=sum(r['travel'] for r in ok),
        wait=sum(r['wait'] for r in ok),
        disposal=sum(r['disposal'] for r in ok),
        late=sum(r['late'] for r in ok),
        trips=len(ok),
        tons=sum(r['tons'] for r in ok),
    )


def precheck(orders, depots):
    """模块 A': 视觉置信度分诊, 输出自动调度队列与人工复核队列。"""
    auto, manual = [], []
    for o in orders:
        if o['conf'] < CONF_GATE:
            manual.append((o['id'], o['conf'], '置信度低于 %.2f' % CONF_GATE))
            continue
        if not feasible_depots(o, depots):
            manual.append((o['id'], o['conf'], '无接收设施匹配材质 ' + o['mat']))
            continue
        auto.append(o)
    return auto, manual

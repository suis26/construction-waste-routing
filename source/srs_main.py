# -*- coding: utf-8 -*-
"""SRS-Route 主程序: 复现 PPT 第 9 页案例, 并跑五类建筑垃圾扩展场景。"""
import os, sys, json, csv
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from srs_data import ppt_case, expanded_case, MATERIAL_REUSE
from srs_core import (precheck, feasible_depots, route_cost, all_direct, consolidate, total_metrics, CONF_GATE, COST_PER_KM, FIXED_TRIP_COST)
OUT = os.path.abspath(os.path.join(HERE, '..', 'output'))


def hhmm(m):
    m = int(round(m))
    return '%02d:%02d' % (m // 60, m % 60)


def run_ppt_case(P):
    orders, depots, vehicles = ppt_case()
    omap = {o['id']: o for o in orders}
    P('=' * 88)
    P('一、复现 PPT 第 9 页案例')
    P('=' * 88)
    P('场景: A/B/C 各 4 吨同类来料(混凝土砖瓦), 12 吨车, D 处理厂兼作发车点')
    P('成本参数: 出车固定 %.0f 元/趟 + %.0f 元/km' % (FIXED_TRIP_COST, COST_PER_KM))
    direct = []
    for o in orders:
        c = route_cost('D', [o['id']], vehicles, depots, omap, vehicles[0])
        c['vehicle'] = 'V1'
        direct.append(c)
    md = total_metrics(direct)
    P('')
    P('[分别直送] D-A-D / D-B-D / D-C-D, 共 %d 趟' % md['trips'])
    P('   总里程 %.0f km, 运输成本 %.0f 元' % (md['km'], md['travel']))
    P('   A 点来料到达处理厂: %s' % hhmm(direct[0]['arrive']))
    cons = route_cost('D', ['A', 'B', 'C'], vehicles, depots, omap, vehicles[0])
    cons['vehicle'] = 'V1'
    P('')
    P('[多点集运] D-A-B-C-D, 共 1 趟')
    P('   总里程 %.0f km, 运输成本 %.0f 元' % (cons['km'], cons['travel']))
    P('   A 点来料到达处理厂: %s' % hhmm(cons['arrive']))
    P('')
    P('   对比: 里程 -%.0f km, 成本 -%.0f 元, A 点延迟 +%.0f 分钟' % (md['km'] - cons['km'], md['travel'] - cons['travel'], cons['arrive'] - direct[0]['arrive']))
    return dict(direct_km=md['km'], direct_cost=md['travel'], direct_arrive=hhmm(direct[0]['arrive']), cons_km=cons['km'], cons_cost=cons['travel'], cons_arrive=hhmm(cons['arrive']))



def run_expanded(P):
    orders, depots, vehicles = expanded_case()
    omap = {o['id']: o for o in orders}
    P('')
    P('=' * 88)
    P('二、五类建筑垃圾扩展场景')
    P('=' * 88)
    P('规模: %d 个产生点, %d 个处理设施, %d 台车, 总产生量 %.1f 吨' % (len(orders), len(depots), len(vehicles), sum(o['tons'] for o in orders)))
    auto, manual = precheck(orders, depots)
    P('')
    P('[模块 A] 视觉预检分诊 (置信度门槛 %.2f)' % CONF_GATE)
    P('   进入自动调度 %d 单' % len(auto))
    for oid, conf, why in manual:
        P('   转人工复核: %s (置信度 %.2f) %s' % (oid, conf, why))
    base = all_direct(auto, depots, vehicles, omap)
    mb = total_metrics(base)
    P('')
    P('[基线] 每单直送, 就近可行设施')
    P('   趟次 %d, 里程 %.1f km, 综合成本 %.0f 元' % (mb['trips'], mb['km'], mb['cost']))
    P('   构成: 行驶 %.0f | 等待 %.0f | 处置 %.0f | 违约 %.0f' % (mb['travel'], mb['wait'], mb['disposal'], mb['late']))
    merged = consolidate(base, vehicles, depots, omap)
    mm = total_metrics(merged)
    P('')
    P('[模块 B] 多点送一点集运 (载重/容积/材质/时间窗/卸货顺序 同时约束)')
    P('   趟次 %d, 里程 %.1f km, 综合成本 %.0f 元' % (mm['trips'], mm['km'], mm['cost']))
    P('   构成: 行驶 %.0f | 等待 %.0f | 处置 %.0f | 违约 %.0f' % (mm['travel'], mm['wait'], mm['disposal'], mm['late']))
    if mb['cost'] > 0:
        P('   >>> 相对直送: 成本 -%.2f%%, 里程 -%.2f%%, 趟次 %d -> %d' % ((mb['cost'] - mm['cost']) / mb['cost'] * 100, (mb['km'] - mm['km']) / mb['km'] * 100, mb['trips'], mm['trips']))


    P('')
    P('[模块 C] 接收匹配: 材质标签 -> 设施接收目录')
    P('   %-4s %-8s %-10s %7s  %s' % ('订单', '类别', '材质', '吨位', '可去向'))
    for o in sorted(auto, key=lambda z: z['id']):
        ds = feasible_depots(o, depots)
        P('   %-4s %-8s %-10s %7.1f  %s' % (o['id'], o['cat'], o['mat'], o['tons'], ','.join(d['id'] for d in ds) or '无'))
    P('')
    P('   材质利用方向(对应 PPT 第 14 页):')
    for m in sorted({o['mat'] for o in auto}):
        P('      %-10s -> %s' % (m, MATERIAL_REUSE.get(m, '需进一步确认')))
    P('')
    P('[调度明细]')
    P('   %-4s %-8s %7s  %-26s %8s %9s  %s' % ('车次', '去向', '吨位', '装卸顺序(到达)', '里程km', '成本元', '状态'))
    rows = []
    for i, r in enumerate(merged, 1):
        if r.get('depot') is None:
            continue
        seq = ' -> '.join('%s(%s)' % (oid, hhmm(t)) for oid, t in r['seq'])
        flag = ('违约%.1fh' % r['late_h']) if r['late_h'] > 0 else '准时'
        P('   %-4d %-8s %7.1f  %-26s %8.1f %9.0f  %s' % (i, r['depot'], r['tons'], seq, r['km'], r['total'], flag))
        rows.append(dict(trip=i, depot=r['depot'], vehicle=r.get('vehicle', ''), tons=round(r['tons'], 2), km=round(r['km'], 2), arrive=hhmm(r['arrive']), cost=round(r['total'], 1), wait_h=round(r['wait_h'], 2), late_h=round(r['late_h'], 2), seq='|'.join(o for o, _ in r['seq'])))


    manifests = []
    mid = 0
    for i, r in enumerate(merged, 1):
        if r.get('depot') is None:
            continue
        for oid, t in r['seq']:
            mid += 1
            o = omap[oid]
            manifests.append(dict(联单号='SR%05d' % mid, 车次=i, 类别=o['cat'], 材质=o['mat'], 起点=oid, 终点=r['depot'], 载重吨=o['tons'], 装车时刻=hhmm(t), 预计到厂=hhmm(r['arrive'])))
    P('')
    P('[模块 D] 联单与调度同源: 生成 %d 张电子联单' % len(manifests))
    return dict(auto=len(auto), manual=len(manual), base=mb, merged=mm, rows=rows, manifests=manifests)


def main():
    os.makedirs(OUT, exist_ok=True)
    lines = []
    P = lines.append
    ppt = run_ppt_case(P)
    exp = run_expanded(P)
    print('\n'.join(lines))
    with open(os.path.join(OUT, 'srs_console.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    with open(os.path.join(OUT, 'srs_schedule.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['trip', 'depot', 'vehicle', 'tons', 'km', 'arrive', 'cost', 'wait_h', 'late_h', 'seq'])
        w.writeheader(); w.writerows(exp['rows'])
    with open(os.path.join(OUT, 'srs_manifests.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['联单号', '车次', '类别', '材质', '起点', '终点', '载重吨', '装车时刻', '预计到厂'])
        w.writeheader(); w.writerows(exp['manifests'])
    with open(os.path.join(OUT, 'srs_result.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(ppt_case=ppt, expanded=dict(auto=exp['auto'], manual=exp['manual'], base=exp['base'], merged=exp['merged'])), f, ensure_ascii=False, indent=2)
    print('\n输出目录: ' + OUT)


if __name__ == '__main__':
    main()


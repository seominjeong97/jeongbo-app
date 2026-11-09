import calendar
import html
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="생활용품 알리미", page_icon="🧴", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""<style>
#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none}
.block-container{max-width:480px;padding:0.65rem 0.8rem 0.5rem!important}
[data-testid="stVerticalBlock"]{gap:.35rem}
h1{font-size:1.35rem!important;padding:0!important;margin:0!important}
p{margin-bottom:.2rem}div[data-testid="stMetric"]{padding:0}
.stButton button{min-height:2.2rem;padding:.15rem .4rem;font-size:.85rem}
[data-testid="stPopover"] button{min-height:2.2rem}
.cal{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:2px;font-size:12px;text-align:center}
.cal th{height:20px;color:#64748b;font-weight:500}
.cal td{height:33px;border-radius:6px;background:#f1f5f9;vertical-align:top;padding:2px 0;line-height:13px}
.cal td.empty{background:transparent}.cal td.today{outline:1.5px solid #0d9488;outline-offset:-1px}
.cal td.due{background:#ccfbf1}.cal td.old{background:#fee2e2}
.cal small{display:block;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 2px;color:#115e59}
.hint{font-size:11px;color:#64748b;line-height:1.35}.stats{font-size:12px;background:#f0fdfa;padding:7px 10px;border-radius:9px;color:#115e59}
@media(max-width:480px){.block-container{padding-top:.4rem!important}.cal td{height:30px}}
</style>""", unsafe_allow_html=True)

# 같은 비밀 주소(home)를 가진 기기끼리 같은 목록을 봅니다.
# QR에는 배포 주소 뒤의 ?home=...까지 포함하세요. 로그인 인증을 대체하지 않습니다.
home = st.query_params.get("home", "")
try:
    home = str(uuid.UUID(home))
except (ValueError, AttributeError, TypeError):
    home = str(uuid.uuid4())
    st.query_params["home"] = home

# Community Cloud의 로컬 파일은 재배포/재생성 시 사라질 수 있습니다.
# 장기 운영은 영구 DB로 변경하세요. 경로는 ITEM_DB_PATH로 지정할 수 있습니다.
DB_PATH = Path(os.environ.get("ITEM_DB_PATH", "items.db"))

def connect():
    db = sqlite3.connect(str(DB_PATH), timeout=15)
    db.row_factory = sqlite3.Row
    return db

with connect() as db:
    db.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, home TEXT NOT NULL, name TEXT NOT NULL, last_date TEXT NOT NULL, cycle INTEGER NOT NULL CHECK(cycle>0), due_date TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, home TEXT NOT NULL, done_date TEXT NOT NULL, previous_last TEXT NOT NULL, previous_due TEXT NOT NULL)")

def get_items():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM items WHERE home=? ORDER BY due_date, name", (home,))]

def upsert(item_id, name, last, cycle):
    due = last + timedelta(days=int(cycle))
    with connect() as db:
        db.execute("INSERT INTO items VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,last_date=excluded.last_date,cycle=excluded.cycle,due_date=excluded.due_date WHERE items.home=excluded.home", (item_id,home,name,last.isoformat(),int(cycle),due.isoformat()))

def complete(item_id):
    with connect() as db:
        row = db.execute("SELECT * FROM items WHERE id=? AND home=?",(item_id,home)).fetchone()
        if row is None:
            return
        if row['last_date'] == date.today().isoformat():
            st.toast("오늘 이미 관리한 물품이에요.")
            return
        today = date.today()
        db.execute("INSERT INTO history (item_id,home,done_date,previous_last,previous_due) VALUES (?,?,?,?,?)",(item_id,home,today.isoformat(),row['last_date'],row['due_date']))
        db.execute("UPDATE items SET last_date=?,due_date=? WHERE id=? AND home=?",(today.isoformat(),(today+timedelta(days=row['cycle'])).isoformat(),item_id,home))
    st.session_state['undo_id'] = item_id

@st.dialog("생활용품 등록 · 수정")
def editor(item=None):
    with st.form("item_form"):
        name = st.text_input("물품 이름",value=item['name'] if item else "",max_chars=40,placeholder="예: 샤워기 필터")
        a,b = st.columns(2)
        last = a.date_input("마지막 교체일",value=date.fromisoformat(item['last_date']) if item else date.today(),min_value=date(2000,1,1),max_value=date.today())
        cycle = b.number_input("교체 주기 (일)",min_value=1,max_value=3650,value=int(item['cycle']) if item else 30,step=1)
        st.caption("다음 교체일: " + (last+timedelta(days=int(cycle))).strftime('%Y.%m.%d') + " · 주기는 제품 안내에 맞춰 설정하세요.")
        save = st.form_submit_button("저장",type="primary",use_container_width=True)
    if save:
        if not name.strip():
            st.error("물품 이름을 입력해 주세요.")
        else:
            upsert(item['id'] if item else str(uuid.uuid4()),name.strip(),last,cycle)
            st.rerun()
    if item:
        confirm = st.checkbox("이 물품과 교체 기록을 삭제합니다")
        if st.button("물품 삭제",disabled=not confirm,use_container_width=True):
            with connect() as db:
                db.execute("DELETE FROM history WHERE item_id=? AND home=?",(item['id'],home))
                db.execute("DELETE FROM items WHERE id=? AND home=?",(item['id'],home))
            st.rerun()

items = get_items()
today = date.today()
overdue = sum(date.fromisoformat(x['due_date']) < today for x in items)
soon = sum(today <= date.fromisoformat(x['due_date']) <= today+timedelta(days=7) for x in items)
header,add = st.columns([3,1])
header.markdown("# 🧴 생활용품 알리미")
if add.button("＋ 등록",use_container_width=True):
    editor()
st.markdown(f'<div class="stats">등록 <b>{len(items)}</b>개　·　기한 지남 <b>{overdue}</b>개　·　7일 이내 <b>{soon}</b>개</div>',unsafe_allow_html=True)

if 'month' not in st.session_state:
    st.session_state.month = today.replace(day=1)

def move_month(delta):
    current = st.session_state.month
    number = current.year*12+current.month-1+delta
    if 2000*12 <= number < 2101*12:
        st.session_state.month = date(number//12,number%12+1,1)

left,title,right,reset = st.columns([1,3,1,1.3])
left.button("‹",on_click=move_month,args=(-1,),use_container_width=True)
m = st.session_state.month
title.markdown(f"<div style='text-align:center;padding-top:7px;font-weight:700'>{m.year}년 {m.month}월</div>",unsafe_allow_html=True)
right.button("›",on_click=move_month,args=(1,),use_container_width=True)
if reset.button("이번 달",use_container_width=True):
    st.session_state.month = today.replace(day=1)
    st.rerun()

by_date = {}
for item in items:
    by_date.setdefault(item['due_date'],[]).append(item)
cal = '<table class="cal"><thead><tr>'+''.join(f'<th>{d}</th>' for d in ['월','화','수','목','금','토','일'])+'</tr></thead><tbody>'
for week in calendar.Calendar(firstweekday=0).monthdayscalendar(m.year,m.month):
    cal += '<tr>'
    for day in week:
        if not day:
            cal += '<td class="empty"></td>'
            continue
        d = date(m.year,m.month,day)
        entries = by_date.get(d.isoformat(),[])
        classes = []
        if entries: classes.append('old' if d < today else 'due')
        if d == today: classes.append('today')
        names = ', '.join(x['name'] for x in entries)
        label = html.escape(entries[0]['name']) if entries else ''
        if len(entries)>1: label += f" +{len(entries)-1}"
        cal += f'<td class="{" ".join(classes)}" title="{html.escape(names,quote=True)}">{day}<small>{label}</small></td>'
    cal += '</tr>'
cal += '</tbody></table>'
st.markdown(cal,unsafe_allow_html=True)
st.markdown('<div class="hint">청록: 교체 예정 · 분홍: 기한 지남 · 테두리: 오늘<br>달력에는 각 물품의 다음 교체일을 표시합니다.</div>',unsafe_allow_html=True)

if items:
    lookup = {x['id']:x for x in items}
    def label(item_id):
        x = lookup[item_id]
        delta = (date.fromisoformat(x['due_date'])-today).days
        status = f'{-delta}일 지남' if delta<0 else ('오늘' if delta==0 else f'D-{delta}')
        return f"{x['name']} · {x['due_date'][5:].replace('-','/')} · {status}"
    selected = st.selectbox("관리할 물품",list(lookup),format_func=label,label_visibility="collapsed")
    row = lookup[selected]
    st.markdown(f"<div class='hint'>최근 교체 {row['last_date']} · {row['cycle']}일 주기</div>",unsafe_allow_html=True)
    done,edit,more = st.columns([2,1,1])
    if done.button("✓ 오늘 교체 완료",type="primary",use_container_width=True):
        complete(selected)
        st.rerun()
    if edit.button("수정",use_container_width=True):
        editor(row)
    with more.popover("기록",use_container_width=True):
        with connect() as db:
            history = db.execute("SELECT done_date FROM history WHERE item_id=? AND home=? ORDER BY id DESC LIMIT 10",(selected,home)).fetchall()
        st.write(row['name'])
        if history:
            for h in history: st.caption(h['done_date']+' 교체 완료')
        else:
            st.caption("아직 완료 기록이 없습니다.")
else:
    st.info("＋ 등록을 눌러 첫 생활용품을 추가해 주세요.")

if st.session_state.get('undo_id'):
    if st.button("↶ 방금 완료 취소",use_container_width=True):
        with connect() as db:
            h = db.execute("SELECT * FROM history WHERE item_id=? AND home=? ORDER BY id DESC LIMIT 1",(st.session_state.undo_id,home)).fetchone()
            if h:
                db.execute("UPDATE items SET last_date=?,due_date=? WHERE id=? AND home=?",(h['previous_last'],h['previous_due'],h['item_id'],home))
                db.execute("DELETE FROM history WHERE id=? AND home=?",(h['id'],home))
        st.session_state.pop('undo_id',None)
        st.rerun()

with st.popover("ⓘ QR 접속 · 저장 안내",use_container_width=True):
    st.caption("배포 후 주소창의 전체 주소(?home=… 포함)를 복사해 QR로 만드세요. 같은 주소로 접속한 가족은 같은 목록을 사용합니다. 새 주소에는 빈 목록이 표시됩니다.")
    st.caption("이 주소는 비밀 공유 링크입니다. 공개하지 마세요. 로그인 기능은 없으며, 민감한 정보는 입력하지 마세요.")
    st.caption("알림은 앱을 열었을 때 표시됩니다. 앱이 닫혀 있을 때의 푸시·문자 알림은 지원하지 않습니다. 날짜는 서버 기준입니다.")
    st.caption("현재는 로컬 SQLite 저장입니다. Community Cloud 재배포·서버 재생성 시 데이터가 사라질 수 있으므로 장기 운영에는 영구 DB 연결이 필요합니다.")
    st.caption("기본 화면은 모바일에 맞춰 압축했습니다. 작은 화면, 글자 확대, 물품 등록·기록 팝업에서는 스크롤이 생길 수 있습니다.")

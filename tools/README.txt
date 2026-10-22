MEZBON — CHEK-PRINTER AGENTI (kassa kompyuteri uchun, Windows)
================================================================

Bu agent kassa kompyuterida ishlaydi va bulutdagi serverdan kelgan
cheklarni mahalliy tarmoqdagi printerga (IP:9100) chiqaradi.

Agent ORQA FONDA, OYNASIZ ishlaydi. Kompyuter yonishi bilan o'zi ishga
tushadi, ishlamay qolsa Windows uni o'zi qayta tiklaydi, va FAQAT
stop_agent.bat buyrug'i bilan to'xtaydi. Hech qanday ko'rinadigan
"qora oyna" (cmd) ochilmaydi.


BIR MARTALIK O'RNATISH
----------------------
1) Python 3 ni o'rnating:  https://python.org
   O'rnatishda "Add Python to PATH" katagini BELGILANG.

2) Buyruq qatorida (cmd) kutubxonani o'rnating:
       pip install websockets

3) agent_config.example.json faylini nusxalab,
   "agent_config.json" deb nomlang va qiymatlarni to'ldiring:
       {
         "rid": 1,
         "token": "POS_BRIDGE_TOKEN-bu-yerga"
       }
   (RID va TOKEN ni administratordan oling.)

4) install_agent.bat ni ikki marta bosing.
   "Administrator huquqi" so'ralsa — HA (Yes) deng.
   Tamom. Agent o'rnatildi va ishga tushdi.


KUNDALIK BOSHQARUV (hammasi ikki marta bosib ishlaydi)
------------------------------------------------------
  install_agent.bat    — o'rnatish / qayta o'rnatish
  stop_agent.bat       — to'xtatish (faqat shu buyruq bilan to'xtaydi)
  start_agent.bat      — qayta ishga tushirish
  status_agent.bat     — holat va oxirgi 20 ta log
  uninstall_agent.bat  — butunlay olib tashlash


SOZLASH / TEKSHIRISH (konsol rejimi)
------------------------------------
Agent nimalar qilayotganini ekranda ko'rish uchun:
  start_xprinter_agent.bat   (ko'rinadigan oynada ishlaydi — faqat sinov uchun)
yoki:
  python xprinter_agent.py


LOG FAYLI
---------
Orqa fonda ishlaganda barcha hodisalar shu yerga yoziladi:
  C:\ProgramData\MezbonPrinter\agent.log
(status_agent.bat oxirgi qatorlarini ko'rsatadi.)


TEZ-TEZ BERILADIGAN SAVOLLAR
----------------------------
S: Oyna yopilsa agent to'xtaydimi?
J: Yo'q. Hech qanday oyna yo'q — agent xizmat sifatida orqa fonda ishlaydi.

S: Kompyuter o'chib-yonsa?
J: O'zi qayta ishga tushadi (login shart emas).

S: Qanday qilib butunlay to'xtataman?
J: stop_agent.bat (vaqtincha) yoki uninstall_agent.bat (butunlay).

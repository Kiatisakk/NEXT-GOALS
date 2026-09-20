# ข้อมูลสาธารณะสำหรับทดลอง NEXT GOAL DP POC

ตรวจแหล่งข้อมูลเมื่อ 20 กันยายน 2026 โดยอ้างจากหน้าของผู้เผยแพร่ข้อมูลโดยตรง ข้อมูลทั้งสองแหล่งเป็น **ข้อมูลสังเคราะห์** ไม่มีเป้าหมายการเงินจริงหรือความน่าจะเป็นของเหตุการณ์ในอนาคต จึงเหมาะกับการทดสอบการแปลงข้อมูลและพฤติกรรมของตัวแก้ปัญหา ไม่ใช่หลักฐานว่าคำแนะนำแม่นยำกับลูกค้าไทย

## 1. ดาวน์โหลดแล้วทดลองได้ทันที: MoneyFlow sample statement

- **ไฟล์:** [sample_statement.csv](https://raw.githubusercontent.com/leotemtem/MoneyFlow/refs/heads/main/sample_data/sample_statement.csv) จาก [โครงการ MoneyFlow](https://github.com/leotemtem/MoneyFlow) มี 30 ธุรกรรมระหว่างวันที่ 1–30 ธันวาคม 2024 รวมเงินเดือน รายจ่ายประจำ และรายรับฟรีแลนซ์
- **ฟิลด์:** `Date`, `Description`, `Amount`, `Balance` โดยจำนวนเงินบวกคือเงินเข้า ลบคือเงินออก และ `Balance` คือยอดหลังรายการ ตาม [เอกสารรูปแบบ CSV ของเจ้าของโครงการ](https://github.com/leotemtem/MoneyFlow#csv-format) และ [ข้อมูลในไฟล์จริง](https://raw.githubusercontent.com/leotemtem/MoneyFlow/refs/heads/main/sample_data/sample_statement.csv)
- **สิทธิ์ใช้:** ผู้เผยแพร่ระบุว่าไฟล์ใน `sample_data/` เป็นข้อมูลสังเคราะห์ และโครงการเผยแพร่ภายใต้ [MIT Licence](https://github.com/leotemtem/MoneyFlow#licence) หากคัดลอกหรือแจกจ่ายไฟล์ ให้เก็บข้อความลิขสิทธิ์/ใบอนุญาตของต้นทางไว้
- **ข้อจำกัด:** มีเพียงเดือนเดียว ไม่มีสกุลเงินใน CSV ไม่มีเป้าหมายการเงินหรือ probability และไม่มีรายการในอนาคตหลัง 30 ธันวาคม 2024 ชื่อร้านค้าและค่าใช้จ่ายไม่ได้จำลองบริบทไทย จึงเหมาะสำหรับ smoke test ระยะ `horizon_months=1` เท่านั้น

**วิธีแมปเข้า POC:** กำหนดวันเริ่มแผนเป็น 1 ธันวาคม 2024, `month=1`, `day=Date.day`, `amount=Amount`, `label=Description`; `Balance` ใช้ตรวจ reconciliation ไม่ควรเพิ่มเป็น cashflow อีกครั้ง ยอดเปิดบัญชีที่อนุมานจากแถวแรกคือ `3500 - 3500 = 0` หน่วยเงินตามไฟล์ต้นฉบับ กำหนด `initial_cash=0` และ `reserve_min=0` สำหรับ smoke test ชุดนี้ หรือเริ่มหลังวันที่ 1 โดยใช้ยอด snapshot และตัดรายการก่อน snapshot ออก **หลังแก้ปัญหา as-of date ของ POC** เป้าหมายใน `goals` ต้องสร้างขึ้นเอง อย่าอ้างว่าเป็นเป้าหมายที่ติดมากับข้อมูล รูปแบบ JSON ของตัวแก้ปัญหาอยู่ใน [DP_POC_README.md](DP_POC_README.md#json-input)

## 2. ทางเลือกสำหรับทดสอบหลายเดือน: Synthetic Financial Data Generator

- **ต้นทางและวิธีรับข้อมูล:** [repository ของผู้สร้าง](https://github.com/kavyaturlapati/Synthetic-Financial-Data-Generator-Feature-Pipeline) มีคำสั่งสร้าง CSV แบบกำหนด seed, จำนวนผู้ใช้ และช่วงวันที่ได้ เช่น `python -m synthfin.pipeline --users 10 --start 2024-01-01 --end 2024-06-30 --seed 42 --out data --format csv` หลังติดตั้ง `requirements.txt` ตาม [Quick start](https://github.com/kavyaturlapati/Synthetic-Financial-Data-Generator-Feature-Pipeline#quick-start)
- **ฟิลด์ที่ใช้:** ตาราง `accounts` มี `account_id`, `user_id`, `account_type`, `starting_balance`; ตาราง `transactions` มี `timestamp`, `account_id`, `amount`, `txn_type`, `is_recurring`, `balance_after`; ตาราง `balances` มียอดรายเดือน ตาม [data model และ sign convention ของผู้สร้าง](https://github.com/kavyaturlapati/Synthetic-Financial-Data-Generator-Feature-Pipeline#what-gets-generated-data-model) จำนวนเงินบวก/ลบคือผลต่อยอดบัญชี
- **สิทธิ์ใช้:** repository ระบุ [MIT license](https://github.com/kavyaturlapati/Synthetic-Financial-Data-Generator-Feature-Pipeline/blob/main/LICENSE) และบอกว่าข้อมูลที่สร้างทั้งหมดเป็นข้อมูลสังเคราะห์ ไม่มีข้อมูลบุคคลจริง ควรระบุที่มาและเก็บข้อความใบอนุญาตเมื่อแจกจ่ายส่วนของโครงการ
- **จุดแข็ง:** ผู้สร้างจำลองรอบรับเงินเดือนเดือนละสองครั้ง ค่าเช่า ค่าสาธารณูปโภค subscription และรูปแบบใช้เงินที่ต่างกันระหว่างผู้ใช้ พร้อม seed สำหรับทำซ้ำ [ดูรายละเอียดการจำลอง](https://github.com/kavyaturlapati/Synthetic-Financial-Data-Generator-Feature-Pipeline#realism-baked-in)
- **ข้อจำกัด:** ต้องรัน generator ก่อน; แบบจำลองเป็น synthetic และผู้สร้างระบุว่ารายได้ take-home คงที่ ยังไม่มีรายได้ไม่สม่ำเสมอหรือการตกงาน ไม่มี goal labels หรือ scenario probabilities โดยตรง สกุลเงิน/บริบทไทยไม่ได้ระบุเป็นชุด THB ในเอกสารต้นทาง [ดูข้อจำกัดของ generator](https://github.com/kavyaturlapati/Synthetic-Financial-Data-Generator-Feature-Pipeline#limitations--future-work)

**วิธีแมปเข้า POC:** เลือก `user_id` และบัญชี `checking` หนึ่งบัญชี ใช้ `starting_balance` เป็นเงินต้น ณ วันแรกของช่วงข้อมูล และนำเฉพาะธุรกรรมของบัญชีนั้นมาแปลง `timestamp → month/day`, `amount → amount`, `category` หรือ `txn_type → label` ไม่รวมบัญชี credit card เป็นเงินสดและไม่รวมหลายบัญชีเข้าด้วยกันโดยไม่จัดการ transfer ภายในก่อน ตรวจ `balance_after` กับยอดสะสมทุกแถว แล้วค่อยสร้างเป้าหมายและ scenario shock เพิ่มเอง

## วิธีใช้ผลทดลองอย่างถูกต้อง

1. เริ่มด้วย MoneyFlow เพื่อเช็กการอ่าน CSV, เครื่องหมายของจำนวนเงิน, ยอดตั้งต้น และข้อจำกัดสภาพคล่องรายวัน
2. ใช้ generator สำหรับ 3–6 เดือนและหลายลักษณะผู้ใช้ เพื่อทดสอบการเลื่อนเวลาเติมเงินเข้า goals และการตอบสนองต่อรายรับ/รายจ่ายที่เปลี่ยนไป
3. อย่าเรียก historical transaction ว่า forecast: เมื่อแปลงมาเป็น `cashflows` ของ POC ระบบถือว่าเหตุการณ์เหล่านั้นทราบล่วงหน้า ต้องแยกช่วงประวัติออกจากช่วงทดสอบ และสร้าง scenario probabilities/goal preferences ด้วยสมมติฐานที่ประกาศชัด
4. [POC ปัจจุบัน](DP_POC_README.md#json-input) ระบุจำนวนเงินเป็น THB ขณะที่แหล่งข้อมูลเหล่านี้ไม่ได้ยืนยันว่าเป็น THB ต้องใช้หน่วยเงินเดียวกันทั้งไฟล์และระบุว่าเป็นข้อมูลจำลองเชิงโครงสร้าง; อย่าแสดงยอดต้นฉบับเป็น “บาท” โดยตรง

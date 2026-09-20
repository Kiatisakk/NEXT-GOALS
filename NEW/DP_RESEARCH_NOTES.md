# แกะ Dynamic Programming ของ Das et al. เพื่อใช้กับ NEXT GOAL

## แหล่งต้นฉบับและขอบเขต

- Sanjiv R. Das, Daniel N. Ostrov, Anand Radhakrishnan และ Deep Srivastav, *Dynamic Optimization for Multi-Goals Wealth Management*, *Journal of Banking & Finance* 140 (2022), 106192: [PDF จากเว็บไซต์ผู้เขียน](https://srdas.github.io/Papers/MultWealthGoals.pdf), [หน้าวารสาร](https://www.sciencedirect.com/science/article/pii/S0378426621001515). PDF ลงวันที่ 5 มิถุนายน 2021; บทความวารสารตีพิมพ์ปี 2022.
- [Franklin Templeton อธิบายการใช้ DP ใน GOE®](https://www.ftinstitutional.com/articles/2023/multi-asset/how-and-why-goe-uses-dynamic-programming-to-drive-asset-allocation-decisions) และ [ประกาศเปิดตัว GOE ปี 2020](https://www.franklintempleton.co.uk/press-releases/news-room/2020/franklin-templeton-combines-award-winning-research-with-machine-learning-in-new-goals-optimization-engine). เอกสารเหล่านี้ยืนยันแนวทางของผลิตภัณฑ์ แต่ไม่ได้เปิดซอร์สโค้ด GOE จึงไม่ควรเรียก POC ว่าเป็นการทำซ้ำ implementation ของ GOE.

## อัลกอริทึมในงานวิจัยจริง

1. **เวลาและสถานะ:** แบ่งเวลาเป็น `t = 0..T` และใช้ความมั่งคั่ง `W_i` บน grid เป็นสถานะเดียวของ DP. มีเงินสมทบที่กำหนดล่วงหน้า `I(t)`. ในตัวอย่าง paper มีพอร์ตให้เลือก `l` ซึ่งมีผลตอบแทนคาดหมาย `μ_l` และความผันผวน `σ_l`; grid ของ `W` เรียงแบบ logarithmic. [§2.1, §2.4](https://srdas.github.io/Papers/MultWealthGoals.pdf)
2. **ทางเลือกของเป้าหมาย:** เป้าหมายแต่ละรายการ ณ เวลาที่กำหนดมีทางเลือก `ไม่ทำ / ทำบางส่วน / ทำเต็ม` โดยแต่ละทางเลือกมี *cost* และ *utility* ที่สะท้อนความสำคัญต่อเจ้าของเงิน ไม่ใช่ utility ที่คำนวณตรงจากจำนวนเงิน. เมื่อมีหลายเป้าหมายในเวลาเดียวกัน ผู้เขียนสร้างชุดทางเลือกรวม `(c_k(t), u_k(t))` แล้วตัดชุดที่แพงกว่าแต่ได้ utility ไม่สูงกว่า. ต้องเก็บ mapping กลับไปว่าแต่ละชุดทำเป้าหมายใดบ้าง. [§2.2–2.3](https://srdas.github.io/Papers/MultWealthGoals.pdf)
3. **การเปลี่ยนสถานะ:** หลังเลือกชุดเป้าหมาย `k` เงินตั้งต้นสำหรับช่วงถัดไปเป็น `W_i + I(t) − c_k(t)`. Paper ใช้ geometric Brownian motion ของผลตอบแทนพอร์ตเพื่อสร้างความน่าจะเป็น `q(W_j | W_i, c_k, l)` ระหว่าง wealth-grid nodes แล้ว normalize ให้รวมเป็น 1; ผู้เขียนระบุว่าสามารถแทนด้วย stochastic process อื่นที่เป็น Markov ได้. [§3.1](https://srdas.github.io/Papers/MultWealthGoals.pdf)
4. **Bellman backward pass:** ตั้ง `V_T(W_i) = U(W_i)` (ตัวอย่างหลักตั้ง terminal utility เป็นศูนย์) จากนั้นคำนวณย้อนเวลา:

   `V_t(W_i) = max_(k,l) [u_k(t) + Σ_j q(W_j | W_i, c_k(t), l) V_(t+1)(W_j)]`

   บันทึก `k*` และ `l*` ของทุก `(t, W_i)` เป็น *policy* ที่ปรับการตัดสินใจตามระดับเงินที่เกิดขึ้นจริง. [§3.2, สมการ (4)](https://srdas.github.io/Papers/MultWealthGoals.pdf)
5. **Forward pass:** เริ่ม probability mass ที่ `W(0)` แล้วเดินตาม policy เพื่อหาการกระจายของเงินและโอกาสทำได้ของแต่ละเป้าหมาย. Utility weights ปรับได้ตามความเห็นผู้ใช้หลังเห็น trade-off ของโอกาสสำเร็จ. [§2.2, §3.3](https://srdas.github.io/Papers/MultWealthGoals.pdf)

ผู้เขียนรายงานวิธีแยก optimization ของพอร์ตกับชุดเป้าหมายในกรณีใหญ่ และรายงานตัวอย่าง 60 ปีที่ลดเวลา 13 นาทีเหลือ 17 วินาทีบนเครื่องของงานวิจัย; ตัวเลขนี้ **ไม่ใช่ benchmark ของ NEXT GOAL**. [§3.2](https://srdas.github.io/Papers/MultWealthGoals.pdf)

## ย้ายแกนคิดมาเป็น POC กระแสเงินสด 1–24 เดือน

| องค์ประกอบ | การดัดแปลงสำหรับ POC |
| --- | --- |
| สถานะ | `(t, เงินสดที่ใช้ได้, ความคืบหน้าเป้าหมายที่ต้องติดตาม)`; ถ้าเป้าหมายจ่ายครั้งเดียวตามวันแน่นอน เงินสดอย่างเดียวอาจพอ แต่ถ้าเลื่อนวันหรือทยอยออมต้องเพิ่มสถานะเพื่อจำประวัติที่มีผลต่ออนาคต |
| ช่วงเวลา | ใช้ **วันที่มีเหตุการณ์** (วันเงินเข้า ค่าเช่า บิล วันเป้าหมาย) หรืออย่างน้อยตรวจยอดภายในเดือนตามลำดับวัน; ใช้เฉพาะยอดสิ้นเดือนจะพลาดกรณีค่าเช่าครบกำหนดก่อนเงินเดือนเข้า |
| ทางเลือก | กำหนดชุด `ไม่ทำ / ทำบางส่วน / ทำเต็ม` ของเป้าหมายที่ยืดหยุ่นได้ พร้อม cost และ utility ที่ผู้ใช้ตรวจแก้ได้; ค่าเช่า หนี้ถึงกำหนด และค่าใช้จ่ายจำเป็นเป็น **ข้อจำกัดบังคับ** ไม่ใช่เป้าหมายที่ DP ยอมทิ้งเพื่อแลกคะแนน |
| Transition | `cash_next = cash + income_due − essential_due − chosen_goal_payment − transfer`; POC แรกใช้กระแสเงินสดที่ยืนยันแล้ว/สมมติฐานชัดเจนและไม่ต้องมี `l`, `μ`, `σ` ของพอร์ตลงทุน |
| Feasibility | ตัด action ที่ทำให้ยอดหลังรายการใด ๆ ต่ำกว่าเงินสำรองขั้นต่ำ/ข้อจำกัดสภาพคล่อง; ถ้า baseline ก็ขาดเงิน ให้รายงานวันที่และจำนวนที่ขาด แทนการแสดงแผนที่อ้างว่าปลอดภัย |
| Bellman | `V_t(s) = max_(a∈feasible(s)) [u_t(a) + V_(t+1)(next(s,a))]`; เก็บ action เพื่ออธิบายว่าแผนเลือกจ่ายหรือเลื่อนเป้าหมายใด เพราะเหตุใด |
| Transfer Check | ใส่ยอดโอนที่ผู้ใช้กำลังพิจารณาเป็นเหตุการณ์วันนี้ แล้วคำนวณ policy ใหม่ เปรียบเทียบวันถึงเป้าหมายและยอดต่ำสุดกับกรณีไม่โอน |

นี่คือ **DP ที่ดัดแปลงจากหลักการของ paper** ไม่ใช่การคัดลอกสมการความเสี่ยงพอร์ตทั้งชุด. ถ้ากระแสเงินสดเป็น deterministic ผลลัพธ์คือแผนภายใต้สมมติฐาน ไม่ใช่ “โอกาสสำเร็จ” เชิงสถิติ; หากต้องการ probability ต้องกำหนดและตรวจสอบความน่าจะเป็นของสถานการณ์รายรับ/รายจ่ายก่อน. ข้อสรุปนี้ตามโครง transition และ forward probability ใน [§3.1–3.3 ของ paper](https://srdas.github.io/Papers/MultWealthGoals.pdf).

## ข้อจำกัดที่ต้องพูดตรง ๆ

- Paper กำหนดวันของแต่ละเป้าหมายล่วงหน้าและระบุว่าโมเดลในบทความ **ไม่สามารถเลื่อนเป้าหมายไปปีถัดไปโดยอัตโนมัติเมื่อพลาดเป้าหมายเดิม**. การเลื่อนวันใน NEXT GOAL จึงเป็นส่วนขยายที่ต้องเพิ่มสถานะ/ทางเลือกและทดสอบเอง. [§1](https://srdas.github.io/Papers/MultWealthGoals.pdf)
- ผลที่ paper เปรียบเทียบคือวิธี Monte Carlo แบบดั้งเดิมที่ใช้พอร์ตคงที่และทำเป้าหมายเต็มตามลำดับเวลา; ไม่ใช่ข้อพิสูจน์ว่า DP เหนือกว่า Monte Carlo ทุกวิธีหรือทุกชุดข้อมูล. [§1](https://srdas.github.io/Papers/MultWealthGoals.pdf)
- Utility ของแต่ละเป้าหมายต้องสะท้อนความชอบผู้ใช้; paper เสนอให้ปรับน้ำหนักหลังผู้ใช้เห็นโอกาสของแต่ละเป้าหมาย ไม่ได้มีสูตร universal ที่อนุมานความสำคัญจากยอดเงินเพียงอย่างเดียว. [§2.2](https://srdas.github.io/Papers/MultWealthGoals.pdf)

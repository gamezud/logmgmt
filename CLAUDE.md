# Log Management System — Full-Stack Intern Assignment

## บริบท
งาน assignment สมัครฝึกงาน ผู้ทำต้องอธิบายทุกการตัดสินใจในวิดีโอเดโม 30 นาที
เกณฑ์ให้คะแนนรวมข้อ "ability to clearly explain the design rationale"
สภาพแวดล้อม: WSL2 Ubuntu 22.04, Docker, Python 3.10, Node 20

## กฎการทำงาน
1. อธิบายเหตุผลของทุกการตัดสินใจ ระบุทางเลือกอื่นที่ไม่ได้เลือกและเหตุผลที่ไม่เลือก
2. ห้ามใช้ library หรือ pattern ที่ยังไม่ได้อธิบายก่อนใช้
3. เลือกโค้ดที่อ่านง่ายเสมอ แม้จะยาวกว่า ห้ามใช้ one-liner ที่ต้องแกะ
4. แก้ทีละไฟล์ อย่าแก้รวดเดียวหลายสิบไฟล์
5. ทุกครั้งที่ตัดสินใจเรื่องโครงสร้าง ให้เพิ่มบันทึกลงใน docs/DECISIONS.md
   รูปแบบ: บริบท / ตัวเลือกที่พิจารณา / สิ่งที่เลือก / เหตุผล / ข้อเสียที่ยอมรับ
6. หลังแก้โค้ดเสร็จ ให้บอกคำสั่งที่ต้องรันทดสอบ อย่ารันเซิร์ฟเวอร์ค้างไว้เอง

## Stack ที่ล็อกไว้ ห้ามเปลี่ยนโดยไม่ถาม
- Ingest: Python asyncio (syslog UDP+TCP 514), FastAPI (HTTP), CLI loader (file batch)
- Storage: PostgreSQL 16, JSONB + GIN, partition รายวันบน @timestamp, Row-Level Security
- Backend: FastAPI + Pydantic v2, JWT (claims: sub, role, tenant)
- Frontend: React + Vite + Recharts
- Proxy/TLS: Caddy
- Packaging: docker-compose.yml + docker-compose.saas.yml (override)
- Tests: pytest

## ข้อห้ามด้านความปลอดภัย
- tenant ต้องอ่านจาก JWT claim ฝั่ง server เท่านั้น
- ห้ามมี endpoint ใดรับ tenant จาก query param, body หรือ header ของ client
- ทุก query ต้องผ่าน RLS ไม่ใช่แค่ WHERE tenant = ? ในโค้ด
- ห้ามเขียนค่า secret จริงลงไฟล์ใดๆ ใช้ .env.example เท่านั้น

## คำสั่งประจำ
- ติดตั้ง: make install
- รันระบบ: make up
- หยุดระบบ: make down
- เทสต์: make test
- โหลดข้อมูลตัวอย่าง: make seed
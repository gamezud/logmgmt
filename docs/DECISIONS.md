# Decision Log

บันทึกการตัดสินใจเชิงโครงสร้างของ storage layer (`events` table, partitioning, RLS)
ตามรูปแบบที่กำหนดใน `CLAUDE.md`: บริบท / ตัวเลือกที่พิจารณา / สิ่งที่เลือก / เหตุผล / ข้อเสียที่ยอมรับ

หลายรายการด้านล่างพบระหว่างการ implement จริง (ไม่ใช่แค่คิดไว้ล่วงหน้า) —
ยืนยันด้วยการรันทดสอบจริงกับ `postgres:16` container ก่อนเขียนโค้ดสุดท้าย
ไม่ใช่อาศัยความจำ/เอกสารเพียงอย่างเดียว โดยเฉพาะรายการเรื่อง RLS กับ partition

---

## 1. ชื่อคอลัมน์ `@timestamp` → `event_time`

**บริบท:** common schema ของโจทย์ (§3) ระบุ field ชื่อ `@timestamp` แต่ Postgres
ไม่รองรับชื่อคอลัมน์แบบนี้โดยตรง (ต้องใช้ quoted identifier `"@timestamp"` ทุกครั้ง)

**ตัวเลือกที่พิจารณา:**
- (a) ใช้ `"@timestamp"` ตรงตัวใน SQL ทุกจุด (schema, partition key, query)
- (b) เปลี่ยนชื่อคอลัมน์ภายใน DB เป็น `event_time` แล้ว map กลับเป็น `@timestamp`
  เฉพาะที่ HTTP API layer

**สิ่งที่เลือก:** (b) — คอลัมน์ชื่อ `event_time` ภายใน DB

**เหตุผล:** การ quote `"@timestamp"` ทุกครั้งในทุกไฟล์ SQL/Python ในอนาคต
(backend, ingest, tests) เป็นความเสี่ยงต่อ bug ที่ไม่จำเป็น เพราะลืม quote ครั้งเดียว
ก็ error ทันที ส่วน `event_time` เป็น identifier ปกติที่ไม่ต้อง quote เลย
การ map กลับเป็น `@timestamp` ที่ HTTP API ทำครั้งเดียวด้วย Pydantic v2 field alias
(`Field(alias="@timestamp")` บน field ชื่อ `event_time`, พร้อม `populate_by_name=True`)
ดังนั้น JSON เข้า/ออกยังคงเป็น `@timestamp` ตามโจทย์ทุกประการ ส่วน DB/Python
ภายในใช้ `event_time` — เป็นการย้ายความยุ่งยากไปไว้จุดเดียวแทนที่จะกระจายทุกที่

**ข้อเสียที่ยอมรับ:** คนที่มาอ่าน schema ตรงๆ (เช่น `\d events`) จะไม่เห็นชื่อ
`@timestamp` ตามโจทย์ทันที ต้องรู้ mapping นี้ก่อน — แก้ด้วยคอมเมนต์ในทุกจุดที่เกี่ยวข้อง
และบันทึกนี้

---

## 2. Flatten `cloud.*` เป็น `cloud_account_id`, `cloud_region`, `cloud_service`

**บริบท:** common schema มี field ซ้อน (`cloud.account_id`, `cloud.region`, `cloud.service`)
ซึ่งมีจุด (`.`) ในชื่อ เช่นเดียวกับปัญหา `@timestamp`

**ตัวเลือกที่พิจารณา:**
- (a) ใช้ quoted identifier `"cloud.account_id"` ตรงตัว
- (b) flatten เป็น snake_case: `cloud_account_id`, `cloud_region`, `cloud_service`

**สิ่งที่เลือก:** (b)

**เหตุผล:** field กลุ่มนี้ใช้บ่อยน้อยกว่า `@timestamp` มาก (ไม่ใช่ partition key,
ไม่ได้ query ทุกครั้ง) ดังนั้นความคุ้มค่าของการรักษาชื่อเดิมไว้ (แลกกับต้อง quote
ทุกครั้ง) ต่ำกว่ากรณี `@timestamp` — เกณฑ์ที่ใช้แยกสองการตัดสินใจนี้คือความถี่ในการใช้งาน

**ข้อเสียที่ยอมรับ:** ไม่ mirror ชื่อ field เดิมของ common schema 100% —
ผู้ implement ingest layer ต้องรู้ว่า `cloud.account_id` (JSON) → `cloud_account_id` (DB column)

---

## 3. ไม่ใส่ CHECK constraint บนคอลัมน์ `action`

**บริบท:** common schema แนะนำค่า `action` เป็น enum: `allow|deny|create|delete|login|logout|alert`

**ตัวเลือกที่พิจารณา:**
- (a) บังคับด้วย `CHECK (action IN (...))` ตาม enum ที่แนะนำ
- (b) ปล่อยเป็น `text` อิสระ ไม่บังคับ

**สิ่งที่เลือก:** (b)

**เหตุผล:** ตัวอย่าง CrowdStrike ในโจทย์เอง (§4.4) ใช้ `action: "quarantine"`
ซึ่งไม่อยู่ใน enum ที่โจทย์แนะนำ — พิสูจน์ว่า enum ที่ให้มาเป็นตัวอย่าง ไม่ใช่ค่าที่ครบถ้วน
ถ้าใส่ CHECK ตาม enum นี้จริง ข้อมูลตัวอย่างจากโจทย์เองจะ insert ไม่ผ่าน

**ข้อเสียที่ยอมรับ:** ไม่มีการบังคับความถูกต้องของค่า `action` ที่ระดับ DB เลย
(typo หรือค่าแปลกๆ จะผ่านเข้ามาได้) — ถ้าต้องการ validation จะต้องทำที่ normalization
layer (ingest) แทน ซึ่งยังไม่ implement ในเซสชันนี้

---

## 4. ใช้ type `inet` สำหรับ `src_ip`/`dst_ip` แทน `text`

**บริบท:** common schema ระบุ `src_ip`, `dst_ip` เป็น string แต่ไม่ได้ระบุ SQL type

**ตัวเลือกที่พิจารณา:** (a) `text` (b) `inet`

**สิ่งที่เลือก:** (b) `inet`

**เหตุผล:** `inet` เป็น native type ของ Postgres สำหรับ IP address รองรับทั้ง IPv4/IPv6,
มี operator สำหรับเปรียบเทียบ subnet (`<<`, `<<=`) ได้ฟรี และ index บน `inet`
มีขนาดเล็ก/เร็วกว่า index บน `text` ของค่าเดียวกัน

**ข้อเสียที่ยอมรับ:** ถ้า ingest layer ส่งค่าที่ไม่ใช่ IP ที่ valid (เช่น hostname
หรือค่าว่างผิดรูปแบบ) จะ insert ไม่ผ่านทันที — ต้อง validate/แปลงค่าที่ normalization
layer ก่อน insert เสมอ

---

## 5. Composite primary key `(id, event_time)` + `identity bigint` แทน UUID

**บริบท:** Postgres partitioned table บังคับให้ partition key ต้องเป็นส่วนหนึ่งของ
unique constraint ใดๆ บนตาราง จึงไม่สามารถใช้ `id` เดี่ยวๆ เป็น PK ได้

**ตัวเลือกที่พิจารณา:**
- surrogate key: (a) `bigint GENERATED ALWAYS AS IDENTITY` (b) `uuid`
- PK: บังคับเป็น composite `(id, event_time)` อยู่แล้วจากข้อจำกัดของ partitioning

**สิ่งที่เลือก:** `id bigint identity` + PK `(id, event_time)`

**เหตุผล:** ตารางนี้ insert ต่อเนื่องตลอดเวลา (log ingestion) — `bigint` แบบ sequential
ทำให้ btree index ของ PK เรียงลำดับการเขียนเป็นธรรมชาติ (insert ท้าย index เสมอ)
ในขณะที่ UUID (แบบสุ่ม) ทำให้การเขียนกระจายทั่ว index แบบสุ่ม เพิ่ม index bloat
และลด cache locality — สำคัญมากสำหรับตารางที่มี write throughput สูง

**ข้อเสียที่ยอมรับ:** `id` เป็นเลขเรียงลำดับที่เดาได้ (enumerable) แต่ยอมรับได้เพราะ
ไม่เคยถูก expose เป็น public identifier และการเข้าถึงข้อมูลถูกควบคุมด้วย RLS
(ไม่ใช่ security-by-obscurity ของ ID)

---

## 6. Role `app_user` แยกจาก `POSTGRES_USER` (superuser)

**บริบท:** โจทย์และ `CLAUDE.md` บังคับว่าทุก query ต้องผ่าน RLS จริง ไม่ใช่แค่
`WHERE tenant = ?` ในโค้ด

**ตัวเลือกที่พิจารณา:**
- (a) ให้ backend เชื่อมต่อด้วย `POSTGRES_USER` (ที่มีอยู่แล้วจาก postgres image)
- (b) สร้าง role ใหม่ `app_user` แบบ non-superuser เฉพาะสำหรับ backend

**สิ่งที่เลือก:** (b)

**เหตุผล:** `POSTGRES_USER` เป็น Postgres superuser ซึ่ง **bypass RLS เสมอ**
ไม่ว่าจะตั้ง `FORCE ROW LEVEL SECURITY` หรือไม่ก็ตาม — ถ้า backend เชื่อมต่อด้วย
role นี้ RLS ทั้งหมดที่สร้างไว้จะไม่มีผลอะไรเลยในทางปฏิบัติ `app_user` ได้สิทธิ์แค่
`SELECT, INSERT` บน `events` (ไม่มี `UPDATE`/`DELETE` เพราะ log ควรเป็น append-only
อยู่แล้ว ช่วยจำกัดความเสียหายถ้า credential รั่วด้วย)

**ข้อเสียที่ยอมรับ:** ต้องดูแล credential เพิ่มอีกชุด (`APP_DB_USER`/`APP_DB_PASSWORD`)
และต้องระวังไม่ให้ future session เผลอใช้ `POSTGRES_USER` จาก backend

---

## 7. RLS policy แบบ fail-closed (`current_setting(..., true)`)

**บริบท:** ต้องกำหนดว่าถ้า backend ลืม set `app.tenant` ก่อน query จะเกิดอะไรขึ้น

**ตัวเลือกที่พิจารณา:**
- (a) `current_setting('app.tenant')` (ไม่มี `true`) — throw error ถ้าไม่เคย set
- (b) `current_setting('app.tenant', true)` — คืนค่า `NULL` ถ้าไม่เคย set

**สิ่งที่เลือก:** (b)

**เหตุผล:** `tenant = NULL` ใน SQL ไม่มีทาง evaluate เป็น `true` ได้เลย (NULL semantics)
ดังนั้นถ้า `app.tenant` ไม่เคยถูก set แถวทุกแถวจะถูกซ่อนไปเอง (0 แถว) — เป็น
fail-closed ที่ปลอดภัยโดยธรรมชาติของ SQL เอง ไม่ต้องเขียน error handling พิเศษ
ทดสอบยืนยันด้วย `tests/test_rls_tenant_isolation.py::test_unset_tenant_sees_no_rows`

**ข้อเสียที่ยอมรับ:** ถ้า backend มี bug ที่ลืม set `app.tenant` จริงๆ จะได้ผลลัพธ์
เป็น "query สำเร็จแต่ไม่มีข้อมูล" ไม่ใช่ error ชัดเจน — ทำให้ debug bug ประเภทนี้ยากกว่า
ตัวเลือก (a) เล็กน้อย แต่ปลอดภัยกว่ามากในแง่ไม่รั่วข้อมูลข้าม tenant

---

## 8. RLS policy ไม่สืบทอดจาก partitioned parent ไปยัง partition (บั๊กที่พบระหว่าง implement)

**บริบท:** สมมติฐานเดิมตอนวางแผนคือ index กับ RLS จะสืบทอดจาก parent table
ไปยัง partition เหมือนกัน — สมมติฐานนี้ถูกท้าทายและตรวจสอบจริงก่อนเขียนโค้ด
ด้วยการรัน `postgres:16` container ทดสอบโดยตรง

**ผลการทดสอบจริง (ไม่ใช่จากเอกสาร):**
1. Query ผ่าน parent table (`SELECT ... FROM events`) ใช้ policy ของ **parent**
   ครอบคลุมทุก partition โดยอัตโนมัติ ไม่ว่า partition นั้นจะมี RLS หรือไม่
2. Query ตรงเข้า partition (`SELECT ... FROM events_2026_09_11`) ใช้ policy
   ของ **partition นั้นเอง** เท่านั้น — ถ้า partition ไม่เคยเปิด RLS เลย
   จะเป็นการ **bypass เต็มรูปแบบ** (เห็นข้อมูลทุก tenant)
3. ถ้า partition เปิด RLS (`ENABLE`/`FORCE`) แต่ไม่มี policy ของตัวเอง
   จะเป็น default-deny (0 แถวสำหรับทุกคน แม้ tenant ที่ถูกต้อง)
4. Index บน parent สืบทอดไปยัง partition (รวมที่สร้างใหม่ภายหลัง) โดยอัตโนมัติ
   — RLS ไม่ทำงานแบบเดียวกัน เป็นจุดที่ต่างกันชัดเจนและง่ายจะเข้าใจผิด

**ตัวเลือกที่พิจารณา:**
- (a) เปิด RLS แค่บน parent table เท่านั้น (ตามสมมติฐานเดิม)
- (b) เปิด RLS + สร้าง policy ซ้ำบนทุก partition ด้วย

**สิ่งที่เลือก:** (b) — ผ่านฟังก์ชัน `apply_tenant_rls(partition_name)` ใน
`02_schema.sql` ที่ idempotent (เช็ค `pg_policies` ก่อนสร้างซ้ำ) เรียกใช้ทั้งจาก
`events_default` ตอน schema init และจาก `create_daily_partitions()` ทุกครั้งที่
สร้าง partition ใหม่

**เหตุผล:** (a) จะทำให้ query ผ่าน parent ปลอดภัย แต่ query ตรงเข้า partition
(เช่น เครื่องมือ admin/backup/report ในอนาคตที่ discover ชื่อ partition จาก
`pg_tables`) จะ bypass tenant isolation ได้เต็มๆ — เป็นช่องโหว่ security ที่ร้ายแรง
และตรวจจับยากเพราะ query ผ่าน parent ปกติจะทำงานถูกต้องเสมอ ไม่มีสัญญาณเตือน

**ข้อเสียที่ยอมรับ:** ต้องดูแล policy สองระดับ (parent + ทุก partition) แทนที่จะ
เขียนครั้งเดียวจบที่ parent — เพิ่มความซับซ้อนของโค้ด SQL แลกกับความถูกต้อง
ได้เพิ่ม regression test เฉพาะเรื่องนี้ไว้ที่
`tests/test_rls_tenant_isolation.py::test_direct_partition_access_is_isolated`
เพื่อให้ถ้ามีใครลบ `PERFORM apply_tenant_rls(...)` ออกในอนาคตจะมี test แดงทันที
(test นี้ตั้งใจ temporarily GRANT บน partition เพื่อบังคับให้ RLS layer เป็นตัว
ตัดสินผลจริงๆ ไม่ใช่ grant layer ที่บังเอิญบัง bug นี้ไว้)

---

## 9. `events_default` partition + ต้นทุนการ lock ตอนสร้าง partition ใหม่

**บริบท:** ต้องมีที่รองรับแถวที่ `event_time` ไม่ตรงกับ partition ไหนที่สร้างไว้ล่วงหน้า
(เช่น clock skew, batch load ข้อมูลเก่า)

**ตัวเลือกที่พิจารณา:**
- (a) ไม่มี default partition — insert ที่ไม่ตรง partition จะ error ทันที
- (b) มี `events_default` เป็น safety net

**สิ่งที่เลือก:** (b)

**เหตุผล:** ingest pipeline ควรจะเสถียร (เป็นหนึ่งในเกณฑ์ให้คะแนน §8 "Ingestion ...
stability") — การให้ insert fail แข็งๆ เพราะ partition ยังไม่ถูกสร้างล่วงหน้าไม่คุ้ม
กับความเสี่ยง

**ข้อเสียที่ยอมรับ (สำคัญ):** การสร้าง partition ใหม่ (`CREATE TABLE ...
PARTITION OF events FOR VALUES ...`) ทุกครั้ง Postgres ต้อง **สแกน default
partition** เพื่อพิสูจน์ว่าไม่มีแถวใน default ที่ควรจะอยู่ใน partition ใหม่นี้
และต้องถือ lock หนักบน default partition ระหว่างสแกนนั้น ถ้า `events_default`
สะสมแถวจำนวนมาก (เช่น scheduler การสร้าง partition ล่วงหน้าหยุดทำงาน หรือ sensor
นาฬิกาเพี้ยนมาก) ทุกครั้งที่ `create_daily_partitions()` รัน จะช้าลงเรื่อยๆ และ
lock นั้นจะไปกระทบ insert ที่กำลังจะตกลง default partition พอดีในช่วงเวลานั้นด้วย
— เป็นความเสี่ยงจริงบนตารางที่รับ log ต่อเนื่องตลอดเวลา

**การลดความเสี่ยง (ยังไม่ทำใน session นี้):** ตั้ง lookahead window ให้กว้างพอ
(ค่า default `days_ahead=7`) เพื่อให้ default แทบไม่ถูกใช้ในทางปฏิบัติ และควร
monitor จำนวนแถวใน `events_default` เป็นสัญญาณเตือน (ยังไม่ implement การ monitor
จริงในเซสชันนี้ เพราะ backend/alerting ยังไม่มี)

---

## 10. Hand-written SQL functions แทน `pg_partman`/`pg_cron`

**บริบท:** ต้องมีกลไกสร้าง/ลบ partition ตามตาราง

**ตัวเลือกที่พิจารณา:**
- (a) extension `pg_partman` (จัดการ partition lifecycle อัตโนมัติเต็มรูปแบบ)
- (b) extension `pg_cron` (schedule SQL ได้ในตัว DB เอง)
- (c) เขียน SQL function เอง (`create_daily_partitions`, `drop_old_partitions`)
  เรียกจากภายนอก (Makefile/cron ในอนาคต)

**สิ่งที่เลือก:** (c)

**เหตุผล:** ข้อกำหนดของ session นี้คือ `docker-compose.yml` มีแค่ postgres image
เปล่าๆ + healthcheck + init script เท่านั้น — extension ทั้งสองตัวต้องการ custom
image หรือขั้นตอน install เพิ่ม ซึ่งขัดกับข้อกำหนดนี้โดยตรง และเป็น "library ที่ยัง
ไม่ได้อธิบาย" ตามกฎข้อ 2 ของ `CLAUDE.md` ด้วย

**ข้อเสียที่ยอมรับ:** lifecycle ที่ได้ไม่ robust เท่า `pg_partman` (เช่น ไม่มี
retry/logging ในตัว, ต้อง schedule เองจากภายนอก) — ยอมรับได้เพราะเป็นโปรเจค demo
ที่ต้องอธิบายทุกจุดได้ใน 30 นาที ฟังก์ชันที่เขียนเองอ่าน/อธิบายง่ายกว่า

---

## 11. Retention ด้วย `DROP TABLE` partition แทน `DELETE`

**บริบท:** โจทย์กำหนด retention อย่างน้อย 7 วัน โดยยอมให้ใช้ deletion, rollover,
หรือ partitioning

**ตัวเลือกที่พิจารณา:** (a) `DELETE FROM events WHERE event_time < X` แบบ scheduled
(b) `DROP TABLE` partition ที่เกินอายุ

**สิ่งที่เลือก:** (b)

**เหตุผล:** `DELETE` ต้อง scan/index-scan หาแถวที่ตรงเงื่อนไข เขียน WAL ต่อแถวที่ลบ
ทิ้ง dead tuple ที่ต้องรอ `VACUUM` มาเก็บพื้นที่คืน และ lock/IO ที่ใช้แปรผันตามจำนวน
ข้อมูล — ยิ่งตารางโตยิ่งช้าลง และแย่งทรัพยากรกับ ingest ที่กำลังเขียนพร้อมกัน
ในขณะที่ `DROP TABLE` partition เป็นการแก้ไข metadata (system catalog) เกือบล้วนๆ
เร็วเกือบจะคงที่ไม่ว่าจะมีกี่แถวในนั้น คืนพื้นที่ดิสก์ทันที ไม่ต้อง `VACUUM`
และ lock แค่ partition นั้นตัวเดียว ไม่กระทบ partition อื่นที่กำลังรับ insert อยู่

**ข้อเสียที่ยอมรับ:** granularity ของการลบข้อมูลคือระดับ "วัน" เท่านั้น
ไม่สามารถลบข้อมูลบางส่วนของวันใดวันหนึ่งแบบละเอียดได้ (ถ้าต้องการ ต้องกลับไปใช้
`DELETE` เฉพาะจุด ซึ่งไม่ใช่ use case ของ retention ปกติ)

---

## 12. Index: เรียง `tenant` นำหน้าเสมอ + ตัด index ที่ไม่จำเป็นออก

**บริบท:** ทุก query ผ่าน RLS ซึ่งกรองด้วย `tenant` เสมอ และ `events` เป็นตารางที่
รับ insert ต่อเนื่องตลอดเวลา (ทุก index ที่มีคือต้นทุนต่อการ insert หนึ่งครั้ง)

**ตัวเลือกที่พิจารณา (index draft แรก):** `(tenant, event_time)`, `(source, event_time)`,
`(event_type, event_time)`, `(severity, event_time)`, `(src_ip)`, `(dst_ip)`,
`("user")`, `(host)` — ทั้งหมดไม่มี `tenant` นำหน้า

**สิ่งที่เลือก (หลังทบทวน):**
- เพิ่ม `tenant` นำหน้าทุก btree index: `(tenant, event_time DESC)`,
  `(tenant, src_ip, event_time DESC)`, `(tenant, "user", event_time DESC)`,
  `(tenant, event_type, event_time DESC)`
- ตัดออก: `dst_ip`, `host`, `severity`, `source` (ไม่มี index แยกให้)

**เหตุผล — ทำไมต้อง `tenant` นำหน้า:** RLS กรอง `tenant` เสมออยู่แล้ว การเรียง
`tenant` เป็นคอลัมน์แรกทำให้ตัว index เองก็แคบขอบเขตลงเหลือแค่ของ tenant นั้น
ไม่ใช่แค่ RLS filter ทำงานทีหลังจาก scan ที่กว้างกว่าที่ควร — สอดคล้องกับ pattern
การใช้งานจริงทุก query 100%

**เหตุผล — ทำไมตัด 4 index ออก:** dashboard ตามโจทย์ (§2.2) ระบุ filter ที่ต้องมี
แค่ time range กับ tenant และ Top-N แค่ IP/User/Event Type เท่านั้น — `dst_ip`,
`host`, `severity`, `source` ไม่มี requirement ชัดเจนรองรับ ในเมื่อ partition ตามวัน
ช่วย prune ข้อมูลไปมากแล้ว การ scan แบบไม่มี index ภายใน partition ของวันเดียว
(ไม่ใช่ทั้งตาราง) ยอมรับได้สำหรับ demo และคุ้มกว่าการจ่ายต้นทุน insert เพิ่มอีก 4
index บนตารางที่ไม่เคยหยุดรับข้อมูล

**ข้อเสียที่ยอมรับ:** ถ้า session ในอนาคตเพิ่ม UI filter ที่ query ด้วย `dst_ip`,
`host`, `severity`, หรือ `source` จริงๆ จะต้องเพิ่ม index คู่นั้นใหม่ (ยังไม่ได้เตรียมไว้
ล่วงหน้า) — เลือกแบบ YAGNI แทนการเผื่อไว้ล่วงหน้าโดยไม่มี requirement รองรับ

---

## 13. GIN `jsonb_ops` (default) แทน `jsonb_path_ops` สำหรับ `raw`, และ GIN บน `_tags`

**บริบท:** ต้อง index เนื้อหาใน `raw jsonb` (field ที่ไม่ได้ promote เป็นคอลัมน์)
กับ `_tags text[]`

**ตัวเลือกที่พิจารณา (สำหรับ `raw`):** (a) GIN `jsonb_path_ops` (เล็กกว่า, เร็วกว่า
แต่รองรับแค่ operator `@>`) (b) GIN `jsonb_ops` (default, ใหญ่กว่า แต่รองรับทั้ง `@>`
และ key-existence `?`/`?|`/`?&`)

**สิ่งที่เลือก:** (b) `jsonb_ops` (default, ไม่ต้องระบุ opclass)

**เหตุผล:** field จาก vendor ต่างๆ (CrowdStrike, AWS, M365, AD) มีโครงสร้างไม่
เหมือนกัน การค้นหาแบบ "มี key นี้อยู่หรือไม่" (`?`) มีประโยชน์พอๆ กับ containment
(`@>`) สำหรับการสำรวจ log แบบ ad-hoc — ข้อมูลขนาด demo ไม่ใหญ่พอที่ความต่างของ
ขนาด index จะเป็นปัญหาจริง

**ข้อเสียที่ยอมรับ:** index ใหญ่กว่าและสร้างช้ากว่า `jsonb_path_ops` — ยอมรับได้ที่
scale ของ demo/assignment นี้ ถ้าข้อมูลโตมากในอนาคตอาจต้องพิจารณาใหม่

**GIN บน `_tags`:** รองรับ query แบบ `_tags @> ARRAY['suspicious']` สำหรับ
tag-based filtering (เช่น alert engine ติด tag ให้ event) — ไม่มีทางเลือกอื่นที่
สมเหตุสมผลกว่าสำหรับ array containment บน Postgres

---

## 14. SQL อยู่ที่ `backend/db/` ไม่ใช่ top-level folder ใหม่

**บริบท:** โจทย์ deliverables (§6) และคำสั่งของ session นี้ระบุโครงสร้าง
`/backend /frontend /ingest /samples /docs /tests` (6 โฟลเดอร์) แต่ session นี้
implement เฉพาะ storage layer ซึ่งยังไม่มี backend code จริง

**ตัวเลือกที่พิจารณา:** (a) สร้างโฟลเดอร์ใหม่ระดับบนสุด เช่น `/db` หรือ `/infra`
(b) วางไว้ใต้ `backend/db/`

**สิ่งที่เลือก:** (b)

**เหตุผล:** backend (FastAPI) จะเป็นเจ้าของการเชื่อมต่อ/migration ของฐานข้อมูลนี้
ในที่สุดอยู่แล้ว การวางไว้ใต้ `backend/` ตั้งแต่แรกสอดคล้องกับความเป็นเจ้าของในระยะยาว
และไม่ต้องขยายจาก 6 โฟลเดอร์ที่ระบุไว้ชัดเจนแล้ว

**ข้อเสียที่ยอมรับ:** คนที่มองหา schema SQL ต้องรู้ก่อนว่ามันอยู่ใต้ `backend/db/`
ไม่ใช่ที่ root ตรงๆ — บรรเทาด้วยลิงก์/คำอธิบายใน `README.md` หลักและ
`backend/db/README.md`

---

## 15. `psycopg` (v3) แทน `psycopg2` สำหรับ pytest

**บริบท:** ต้องเลือก Postgres driver สำหรับ Python เพื่อเขียนเทส (`CLAUDE.md`
ล็อกไว้ว่าต้องอธิบายก่อนใช้ library ใดๆ)

**ตัวเลือกที่พิจารณา:** (a) `psycopg2` (เก่ากว่า, sync-only, ใช้กันมานาน)
(b) `psycopg` v3 (ใหม่กว่า, รองรับ async native, เป็น driver ที่ upstream แนะนำ
ปัจจุบัน)

**สิ่งที่เลือก:** (b)

**เหตุผล:** stack ที่ล็อกไว้ใน `CLAUDE.md` ระบุ backend เป็น FastAPI ซึ่งเป็น async
framework — `psycopg` v3 รองรับ async connection แบบ native ในไลบรารีเดียวกัน
ทำให้ backend session ในอนาคตใช้ driver ตัวเดียวกันกับที่ tests ใช้ตอนนี้ได้เลย
ไม่ต้อง maintain สอง driver

**ข้อเสียที่ยอมรับ:** `psycopg` v3 ใหม่กว่าและผ่านการใช้งานจริงในวงกว้างน้อยกว่า
`psycopg2` เล็กน้อย

---

## 16. `01_roles.sh`: ใช้ stdin heredoc แทน `psql -c`/`-tAc` (บั๊กที่พบระหว่าง implement)

**บริบท:** ต้องสร้าง role `app_user` โดยดึง password จาก environment variable
อย่างปลอดภัย (ไม่ hardcode ลงไฟล์ที่ commit)

**สิ่งที่พบระหว่างทดสอบจริง (ไม่ใช่สมมติฐาน):**
1. Draft แรกห่อ existence-check ไว้ใน `DO $$ ... $$` block — psql **ไม่**
   ทำ variable substitution (`:'var'`) ข้างในบล็อก dollar-quoted เลย ทำให้ข้อความ
   `:'app_user'` ถูกส่งไปที่ server ตรงๆ แล้ว syntax error
2. แก้เป็น `psql -tAc "SELECT ... WHERE rolname = :'app_user'"` แล้วยังพังอยู่ดี
   — ทดสอบแยกส่วนแล้วพบว่า **`-c`/`-tAc` mode ไม่ทำ variable substitution เลย
   ไม่ว่ากรณีใด** มีแต่ stdin (heredoc) และ `-f` (script file) เท่านั้นที่ทำ

**สิ่งที่เลือก:** ทั้ง existence-check และ `CREATE ROLE` ส่งผ่าน stdin heredoc
(`psql ... <<'SQL' ... SQL`) ทั้งคู่ ไม่ใช้ `-c` เลยในสคริปต์นี้

**เหตุผล:** เป็นวิธีเดียวที่ยืนยันแล้วว่า `-v` substitution ทำงานถูกต้องกับทั้ง
query ที่ต้อง capture ผลลัพธ์ (existence check) และ statement ที่ต้องแทรก
identifier/literal อย่างปลอดภัย (`CREATE ROLE`)

**ข้อเสียที่ยอมรับ:** โค้ด shell script อ่านซับซ้อนกว่าการใช้ `-c` แบบบรรทัดเดียว
เล็กน้อย (ต้องมี heredoc 2 จุด) — แลกกับความถูกต้องที่ตรวจสอบแล้วจริง

---

## 17. `make install`/`make test` ใช้ venv ในโปรเจค (`.venv/`) ไม่ใช่ system Python

**บริบท:** ผู้ตรวจจะ clone repo แล้วรันตาม README/Makefile ตรงๆ บนเครื่องของตัวเอง

**ตัวเลือกที่พิจารณา:** (a) `pip install` ตรงเข้า system Python (b) สร้าง
`.venv` ในโปรเจคแล้วติดตั้ง/รันจากใน venv นั้น

**สิ่งที่เลือก:** (b)

**เหตุผล:** Ubuntu 22.04+ (environment ที่ระบุใน `CLAUDE.md`) กำหนดให้ system
Python เป็น "externally-managed-environment" ซึ่ง `pip install` ตรงๆ จะ error
ทันทีโดย default — ผู้ตรวจที่ clone แล้วรัน `make install` จะเจอ environment
พังโดยไม่เกี่ยวกับโค้ดของโปรเจคเลย การสร้าง `.venv` ในโปรเจค (`python3 -m venv .venv`)
แล้วให้ `make test` เรียก `.venv/bin/pytest` ตรงๆ หลีกเลี่ยงปัญหานี้ได้ทั้งหมด
และไม่ไปยุ่งกับ package ระดับ system ของผู้ตรวจด้วย

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียที่มีนัยสำคัญ — `.venv/` ถูกเพิ่มใน `.gitignore`
อยู่แล้วตั้งแต่ scaffold แรก จึงไม่มีความเสี่ยงที่จะ commit venv ลง repo โดยไม่ตั้งใจ

---

## 18. `SET LOCAL app.tenant = %s` ใช้ bind parameter ไม่ได้ (บั๊กที่พบระหว่าง implement ingest layer) — ใช้ `set_config()` แทน

**บริบท:** `ingest/db.py` ต้องตั้งค่า `app.tenant` ด้วยค่าที่มาจากตัวแปร (ไม่ใช่ literal
คงที่แบบใน `tests/test_rls_tenant_isolation.py`) ก่อน insert ทุกครั้ง จึงต้องส่งค่า
tenant ผ่าน bind parameter ของ psycopg เพื่อไม่ให้เปิดช่อง SQL injection

**สิ่งที่พบระหว่างทดสอบจริง (ไม่ใช่สมมติฐาน):** ทดสอบ
`cur.execute("SET LOCAL app.tenant = %s", (tenant,))` กับ `postgres:16` ตรงๆ
ได้ error ทันที: `SyntaxError: syntax error at or near "$1"` — คำสั่ง `SET` ของ
Postgres ไม่รองรับ bind parameter ในตำแหน่งค่า (value) เลย ไม่ว่ากรณีใด
เป็นข้อจำกัดคนละแบบแต่คล้ายกับที่เจอใน `FOR VALUES FROM (%s)` ตอนเขียน
`03_partition_maintenance.sql` (ต้องใช้ `format()`/`%L` แทน)

**ตัวเลือกที่พิจารณา:**
- (a) ต่อสตริงค่า tenant เข้าไปใน SQL ตรงๆ (`f"SET LOCAL app.tenant = '{tenant}'"`)
- (b) ใช้ `SELECT set_config('app.tenant', %s, true)` แทน `SET LOCAL`

**สิ่งที่เลือก:** (b)

**เหตุผล:** (a) เปิดช่องโหว่ SQL injection ผ่านค่า tenant ทันที (แม้ปัจจุบัน tenant
จะมาจากค่าที่ operator/listener กำหนดเอง ไม่ใช่ input จาก client โดยตรง แต่ก็ไม่ควร
เขียนโค้ดที่ไม่ปลอดภัยโดยหลักการ) ส่วน `set_config(setting_name, new_value, is_local)`
เป็นฟังก์ชัน SQL ปกติ ไม่ใช่คำสั่ง `SET` — จึงรับ bind parameter ได้เหมือน query อื่นๆ
ทุกประการ อาร์กิวเมนต์ตัวที่สาม `true` (`is_local`) คือสิ่งที่ทำให้พฤติกรรมเทียบเท่า
`SET LOCAL` ทุกประการ: มีผลแค่ transaction ปัจจุบัน แล้ว reset เมื่อจบ (ดูข้อ 19
เรื่องค่าที่ reset ไปเป็นอะไร)

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียที่มีนัยสำคัญ — `set_config()` เป็นฟังก์ชัน built-in
มาตรฐานของ Postgres เอง ไม่ใช่ library ภายนอก และให้ผลลัพธ์เหมือน `SET LOCAL`
ทุกประการเมื่อ `is_local = true`

---

## 19. หลังจบ transaction ค่า custom GUC (`app.tenant`) กลายเป็น `''` ไม่ใช่ `NULL` (พบระหว่างพิสูจน์ข้อ 18)

**บริบท:** หลังยืนยันว่า `set_config('app.tenant', tenant, true)` ใช้แทน `SET LOCAL`
ได้ ต้องตรวจสอบต่อว่าพฤติกรรม fail-closed ของ RLS (ข้อ 7) ยังใช้ได้จริงหรือไม่
กับ connection ที่ใช้ซ้ำข้าม tenant ต่อเนื่อง (สถานการณ์จริงของ `ingest/syslog_server.py`
ซึ่งเปิด connection เดียวค้างไว้ใช้เขียนทุก tenant)

**ผลการทดสอบจริงกับ `postgres:16` (ไม่ใช่จากเอกสาร):** connection ที่เคย
`set_config('app.tenant', 'test_leak_a', true)` ในทรานแซกชันหนึ่งแล้ว commit ไป —
เมื่อ query `current_setting('app.tenant', true)` นอกทรานแซกชันนั้นในเวลาต่อมา (ไม่ได้
ตั้งค่าใหม่) จะได้ค่าเป็น `''` (string ว่าง) ไม่ใช่ `NULL` เหมือนตอนที่ connection
ไม่เคยแตะ `app.tenant` เลยตั้งแต่แรก — เป็นพฤติกรรมปกติของ Postgres สำหรับ custom
GUC placeholder (parameter ที่ไม่ได้มาจาก extension ที่ registered ไว้ล่วงหน้า):
ค่าที่ตั้งแบบ `is_local` จะ "reset" กลับไปที่ค่าก่อนหน้าของ session เมื่อจบทรานแซกชัน
แต่ถ้า session เองก็ไม่เคยมีค่าที่ registered จริงจัง ค่าที่ reset กลับไปคือ `''`
ไม่ใช่ `NULL` — ยืนยันด้วยสคริปต์ทดสอบตรงและซ้ำอีกครั้งด้วยเทสต์ถาวรใน
`tests/test_db_write_roundtrip.py::test_no_leak_on_same_connection_after_transaction_ends`
(ยืนยันด้วยว่าพฤติกรรมนี้เหมือนกันทั้งกรณีใช้ `SET LOCAL` literal ธรรมดาและ
`set_config()` — ไม่ใช่ผลข้างเคียงจากการเปลี่ยนมาใช้ `set_config()` ในข้อ 18)

**ผลกระทบที่ตรวจสอบแล้ว:** เงื่อนไข RLS `tenant = current_setting('app.tenant', true)`
ยัง fail-closed อยู่ในกรณีนี้ด้วย เพราะ `tenant = ''` ก็ไม่ true เหมือนกัน — **แต่ความ
ปลอดภัยตรงนี้ไม่ได้มาจาก NULL semantics แบบข้อ 7 อีกต่อไป** มันมาจากข้อเท็จจริงว่า
ไม่มี tenant ไหนในตารางเป็นค่าว่างจริงๆ ต่างหาก ซึ่งตอนนั้น (ก่อนข้อ 20) ยังไม่มีอะไร
บังคับไว้ในระดับ DB เลย เป็นแค่ความบังเอิญที่ไม่ควรพึ่งพา — นำไปสู่การเพิ่ม CHECK
constraint ในข้อ 20

**ข้อเสียที่ยอมรับ:** ไม่มี — เป็นการค้นพบพฤติกรรมจริงของ Postgres ที่ต้องรู้ไว้
เพื่อออกแบบ constraint ให้ถูกจุด (ข้อ 20) ไม่ใช่ทางเลือกที่ต้องแลกอะไร

---

## 20. เพิ่ม `CHECK (tenant <> '')` บนคอลัมน์ `events.tenant`

**บริบท:** จากข้อ 19 — การที่ RLS fail-closed ได้เมื่อ `app.tenant` reset เป็น `''`
นั้น ขึ้นอยู่กับสมมติฐาน "ไม่มี tenant ไหนเป็นค่าว่าง" ซึ่งคอลัมน์เดิมมีแค่
`NOT NULL` เท่านั้น — `NOT NULL` ห้ามแค่ `NULL` ไม่ได้ห้าม `''` เลย ทำให้สมมติฐานนี้
เป็นเพียงความบังเอิญ ไม่ใช่สิ่งที่ระบบบังคับจริง

**ตัวเลือกที่พิจารณา:**
- (a) ปล่อยไว้แบบเดิม พึ่งพาว่า application code (Pydantic model / batch loader)
  จะไม่มีวันส่งค่า tenant เป็น `''` เข้ามา
- (b) เพิ่ม `CHECK (tenant <> '')` ที่ระดับ DB โดยตรง

**สิ่งที่เลือก:** (b) — `tenant text NOT NULL CHECK (tenant <> '')`

**เหตุผล:** ความปลอดภัยของ multi-tenant isolation ทั้งระบบพึ่งพาสมมติฐานนี้โดยตรง
(ข้อ 19) การปล่อยให้เป็นแค่ "ความตั้งใจของ application code" ขัดกับหลักการเดียวกับ
ที่ใช้เลือก RLS มาตั้งแต่ข้อ 6/7 ของเอกสารนี้ (ต้องบังคับที่ DB ไม่ใช่แค่ตั้งใจไว้ใน
โค้ด) — `CHECK` ทำให้ "ไม่มี tenant ว่าง" เป็น invariant ที่ DB บังคับจริง ไม่ว่า
จะ insert จากที่ไหน (ingest, batch loader, backend ในอนาคต) หรือแม้แต่ต่อด้วย
superuser ก็ยังโดนปฏิเสธ (ยืนยันด้วยการทดสอบ insert `tenant=''` ผ่าน
`admin_conn` ซึ่ง bypass RLS ได้แต่ไม่ bypass CHECK — เห็น `CheckViolation`
จริง ในเทสต์ `tests/test_db_write_roundtrip.py::test_empty_string_tenant_rejected_by_check_constraint`)

**ข้อเสียที่ยอมรับ:** ต้องทำลาย/สร้าง Postgres volume ใหม่เพื่อให้ init script
รันซ้ำ (schema เปลี่ยนมีผลกับ volume ที่ init ไปแล้วเท่านั้น ไม่กระทบข้อมูลจริงเพราะ
ยังอยู่ในขั้น dev) — ไม่มีข้อเสียเชิง behavior ใดๆ เพราะไม่มี use case ที่ tenant
ควรเป็นค่าว่างอยู่แล้ว

---

## 21. `writer_task` ต้องเก็บ reference ไว้ + `_writer_done` callback ต้องเช็ค `cancelled()` ก่อน `exception()`

**บริบท:** `ingest/syslog_server.py` มี `writer_loop()` เป็น task เดียวที่คอย
ดึงจากคิวแล้วเขียนลง DB (ดูข้อ 11 ในแผน — bounded queue + single writer แทน
per-datagram task) ต้องออกแบบให้ถ้า task นี้ตายกลางทาง ต้องรู้ทันที ไม่ใช่ปล่อยให้
server รับ log เข้าคิวต่อไปเรื่อยๆ โดยไม่มีอะไรถูกเขียนลง DB เลยแบบเงียบๆ

**ปัญหาที่พบระหว่าง implement (ก่อนแก้):**
1. `asyncio.create_task(writer_loop(queue, conn))` ถูกเรียกโดยไม่เก็บ return value
   ไว้ในตัวแปรใดๆ — ตามเอกสาร asyncio เอง task ที่ไม่มีใครถือ reference ไว้เสี่ยงโดน
   garbage collector เก็บไปกลางทางได้ ทำให้ writer หายไปเงียบๆ โดยไม่มี error ใดๆ
2. ไม่มี `add_done_callback` ผูกไว้เลย ต่อให้ task ตายจริง (ด้วยเหตุผลอะไรก็ตาม)
   ก็ไม่มีอะไรแจ้งเตือน

**สิ่งที่เลือก:** เก็บ `writer_task = asyncio.create_task(...)` ไว้เป็นตัวแปรใน `main()`
(มีอายุเท่ากับทั้งโปรแกรม เพราะ `main()` รันจนจบด้วย `serve_forever()` ที่ไม่มีวันคืนค่า)
แล้วผูก `writer_task.add_done_callback(_writer_done)` ซึ่ง `_writer_done` log
ระดับ `CRITICAL` ทุกกรณีที่ task จบ ไม่ว่าจะจบแบบไหน

**เหตุผลที่ต้องเช็ค `task.cancelled()` ก่อนเรียก `task.exception()` เสมอ:** ทดสอบจริง
พบว่าการเรียก `.exception()` บน task ที่ถูก cancel จะ **re-raise `CancelledError`
ออกมาแทนที่จะ return ค่า** — ถ้าเรียก `.exception()` ก่อนโดยไม่เช็ค `cancelled()`
ก่อน จะทำให้ callback เองพังและ error หลุดไปให้ asyncio's default exception
handler จัดการแทน (ข้อความไม่ชัดเจนเท่าที่ตั้งใจไว้)

**ทดสอบจริงยืนยันสองกรณี (ทั้งคู่ log `CRITICAL` ถูกต้อง):**
- กรณี A — `write_event_async` โยน `asyncio.CancelledError` ออกมาเอง (จำลอง
  cancellation ที่หลุดออกมาจาก await ข้างในระหว่างเขียน DB เช่น connection ถูก
  cancel กลางทาง) — `writer_loop`'s `except Exception:` **จับไม่ได้** เพราะ
  `CancelledError` สืบทอดจาก `BaseException` ไม่ใช่ `Exception` (ตั้งแต่ Python 3.8)
  นี่คือเหตุผลหลักที่ callback ระดับนี้ต้องมีอยู่ — ไม่มีทางป้องกันด้วย
  `try/except Exception` ธรรมดาข้างในได้เลย
- กรณี B — เรียก `writer_task.cancel()` จากภายนอกโดยตรง (จำลอง graceful shutdown
  ในอนาคตที่ยังไม่มีในเซสชันนี้)

**สิ่งที่สังเกตเห็นเพิ่มเติมและยอมรับได้:** ทั้งสองกรณีข้างต้นทำให้
`task.cancelled()` เป็น `True` เหมือนกันทุกประการที่ระดับ callback — แยกไม่ออก
ว่าเป็น "cancellation ที่ตั้งใจจากภายนอก" หรือ "CancelledError ที่หลุดมาจากข้างใน
โดยไม่ตั้งใจ" เพราะ Python เอง treat ทั้งสองแบบเหมือนกันในระดับ Task object
ยอมรับได้เพราะผลลัพธ์ที่สำคัญที่สุดเหมือนกันทุกประการ: writer task หยุดทำงาน
ไม่มีอะไรเขียนลง DB อีก และต้องมีคนเข้าไปดู log `CRITICAL` ไม่ว่าสาเหตุจะเป็นอะไร
— การแยกแยะสาเหตุละเอียดกว่านี้ไม่จำเป็นสำหรับ session นี้ (ยังไม่มี graceful
shutdown ให้ต้องแยกจากการ crash จริง)

**ข้อเสียที่ยอมรับ:** log message ของทั้งสองกรณีไม่บอกสาเหตุที่มาต่างกัน (บอกแค่ว่า
"was cancelled") — ถ้าต้องการแยกในอนาคต (เช่น เมื่อมี graceful shutdown จริง)
จะต้องใช้กลไกอื่นเพิ่ม เช่น flag บอกว่ากำลัง shutdown อยู่หรือไม่ ก่อนตัดสินใจว่าจะ
log ระดับ critical หรือแค่ info

---

## 22. ต้องรัน `ingest/syslog_server.py` และ `ingest/batch_loader.py` ด้วย `python -m ingest.xxx` เท่านั้น ห้ามรันเป็น path ตรงๆ (บั๊กที่พบระหว่างทดสอบจริง)

**บริบท:** ทั้งสองไฟล์ทำ `from ingest.db import ...` ซึ่งต้องมี repo root
(ไดเรกทอรีที่มีโฟลเดอร์ `ingest/` อยู่) อยู่ใน `sys.path` ก่อนถึงจะ import
`ingest` เป็น package ได้

**สิ่งที่พบระหว่างทดสอบจริง (ไม่ใช่สมมติฐาน):** รัน
`.venv/bin/python ingest/batch_loader.py samples/api.json` ตรงๆ (จาก repo root)
ได้ `ModuleNotFoundError: No module named 'ingest'` ทันที — สาเหตุคือ Python
เติม **ไดเรกทอรีที่ไฟล์สคริปต์อยู่** (`ingest/`) เข้า `sys.path[0]` เมื่อรันแบบ
`python path/to/script.py` ไม่ใช่ current working directory เหมือนที่คิด
ทำให้ `import ingest.db` กลายเป็นการหา package ชื่อ `ingest` ที่อยู่ *ข้างใน*
`ingest/` เอง (คือ `ingest/ingest/`) ซึ่งไม่มีอยู่จริง — เป็นบั๊กคนละจุดแต่ราก
เดียวกันกับที่พบใน `Makefile`'s `test` target (บันทึกไว้ตอนต้นเซสชันนี้): คำสั่ง
`python -m <module>` เท่านั้นที่เติม current working directory เข้า `sys.path`
ให้อัตโนมัติ การรัน `python <path/to/file>.py` ไม่ทำแบบนั้น

**สิ่งที่เลือก:** เอกสารทุกจุดที่อ้างถึงการรันสองสคริปต์นี้ (README.md ของ `ingest/`,
`Makefile`'s `seed` target, และคำสั่งตรวจสอบท้ายเซสชัน) ต้องใช้รูปแบบ
`python -m ingest.batch_loader <args>` และ `python -m ingest.syslog_server <args>`
เท่านั้น ห้ามใช้ `python ingest/batch_loader.py` แบบ path ตรงๆ เด็ดขาด — ยืนยันแล้วว่า
`python -m ingest.batch_loader ...` ทำงานถูกต้อง (insert สำเร็จ, `event_time` ถูก
rebase, `raw` เก็บ `@timestamp` เดิมไว้ครบ, แถวตกลง partition ของวันจริงไม่ใช่
`events_default`)

**ข้อเสียที่ยอมรับ:** คำสั่งยาวขึ้นเล็กน้อย (`python -m ingest.batch_loader` เทียบกับ
`python ingest/batch_loader.py`) และผู้ใช้ที่คุ้นเคยกับการรัน script แบบ path ตรงๆ
อาจลืมแล้วรันผิดรูปแบบได้ — บรรเทาด้วยการระบุรูปแบบที่ถูกต้องไว้ชัดเจนทุกจุดที่มีการ
พูดถึงคำสั่งนี้ (`ingest/README.md`, `Makefile`, และคำสั่ง verification)

---

## 23. tenant ของ POST /ingest มาจาก JWT claim เท่านั้น ไม่ใช่จาก body แม้ sample ของโจทย์เองจะมี field นี้

**บริบท:** ตัวอย่าง JSON ของ POST /ingest ในโจทย์เอง (§4.3-§4.7) ทุกตัวอย่างมี field
`"tenant"` อยู่ใน body ตรงๆ (เช่น `{"tenant": "demoA", "source": "api", ...}`) ในขณะที่
CLAUDE.md ห้ามชัดเจนว่า "ห้ามมี endpoint ใดรับ tenant จาก query param, body หรือ header
ของ client"

**ตัวเลือกที่พิจารณา:**
- (a) อ่านค่า tenant จาก field ใน body ตรงๆ ตามที่ตัวอย่างของโจทย์แสดงไว้
- (b) เพิกเฉยค่า tenant ใน body ทั้งหมด ใช้ tenant จาก JWT claim ของผู้เรียกเท่านั้นเสมอ

**สิ่งที่เลือก:** (b)

**เหตุผล:** ตัวอย่าง JSON ใน §4.3-§4.7 เป็นเพียง "ตัวอย่างรูปแบบข้อมูล" ไม่ใช่ข้อกำหนดว่า
backend ต้องเชื่อค่านั้น — และข้อกำหนดด้านความปลอดภัยของ CLAUDE.md (และของโจทย์เองใน
§1.3, §2.2 เรื่อง AuthN/AuthZ กับ multi-tenant isolation) มีน้ำหนักเหนือกว่ารูปแบบ JSON
ตัวอย่างเสมอ ถ้า backend เชื่อค่า tenant จาก body จริง ผู้เรียก (แม้ authenticated แล้ว)
จะสามารถใส่ tenant อื่นลงใน body แล้วเขียนข้อมูลเข้าไปยัง tenant ที่ตัวเองไม่มีสิทธิ์ได้
ทันที — เป็นช่องโหว่ multi-tenant isolation ตรงๆ ตัวเดียวกับที่ RLS ทั้งระบบถูกออกแบบมา
ป้องกัน (#6-#8, #18-#20) โค้ดจะ pop key `tenant` ออกจาก body ก่อนส่งต่อให้ `normalize()`
เสมอ โดยไม่สนใจว่ามันจะมีค่าอะไรอยู่

**ข้อเสียที่ยอมรับ:** พฤติกรรมจริงเบี่ยงเบนไปจากตัวอย่าง JSON ในเอกสารโจทย์ตรงๆ —
ผู้ใช้ที่ copy ตัวอย่างมาส่งตรงๆ อาจสับสนว่าทำไม field `tenant` ที่ตัวเองใส่ไปไม่มีผล
ต้องอธิบายจุดนี้ชัดเจนในวิดีโอเดโมและใน README

---

## 24. POST /ingest จำกัดเฉพาะ role admin เท่านั้น — ยอมรับความเสี่ยงที่อุปกรณ์ถือ credential ระดับ admin

**บริบท:** /ingest เป็น endpoint ที่ "เครื่องจักร" เรียก (firewall, agent, collector)
ไม่ใช่คนนั่งหน้าคีย์บอร์ด ต้องตัดสินใจว่า role ไหนเรียกได้บ้าง ในเมื่อ viewer ถูกกำหนด
ไว้แล้วว่า "อ่านได้อย่างเดียว"

**ตัวเลือกที่พิจารณา:**
- (a) admin และ viewer เรียกได้ทั้งคู่
- (b) admin เท่านั้น
- (c) เพิ่ม role ที่สาม `ingestor` ที่เขียนได้อย่างเดียว อ่านไม่ได้เลย (ตรงข้ามกับ viewer)

**สิ่งที่เลือก:** (b) admin เท่านั้น

**เหตุผล:** viewer ถูกนิยามไว้ชัดเจนแล้วว่า "อ่านได้อย่างเดียว" (CLAUDE.md) การให้
viewer เขียนข้อมูลได้ขัดกับนิยามนี้ตรงๆ — จึงเหลือแค่ (b) หรือ (c) ตัวเลือก (c) คือ
ทางแก้ที่ถูกต้องกว่าในระบบจริง เพราะจะทำให้ device ที่ถูกยึด (compromised) รั่วสิทธิ์แค่
"เขียน log ปลอมได้" ไม่ใช่ "มีสิทธิ์ admin เต็ม" (เช่น จัดการ alert rule ในอนาคต) —
เป็นหลักการเดียวกับ least-privilege ที่ใช้เลือก app_user แยกจาก POSTGRES_USER ใน #6
แต่ (c) ถูกปฏิเสธในเซสชันนี้เพราะโจทย์ระบุไว้ตรงๆ ว่า "at least two roles
(Admin/Viewer)" และการเพิ่ม role ที่สามที่ไม่มี requirement รองรับ ขัดกับหลัก YAGNI
แบบเดียวกับที่ใช้ตัด index ที่ไม่จำเป็นออกใน #12 (ตรงนั้นคือ index ตรงนี้คือ role
หลักการเดียวกัน)

**ข้อเสียที่ยอมรับ (สำคัญ ต้องอธิบายในวิดีโอเดโม):** อุปกรณ์ทุกตัวที่ส่ง log เข้าระบบนี้
ถือ JWT ระดับ admin เต็มรูปแบบ — ถ้าอุปกรณ์ตัวใดตัวหนึ่งถูกยึด ผู้โจมตีจะได้สิทธิ์ admin
ทั้งหมดของ tenant นั้น (ไม่ใช่แค่ "เขียน log ปลอมได้" อย่างที่ควรจะเป็นถ้ามี role
`ingestor` แยกต่างหาก) นี่คือจุดอ่อนด้านความปลอดภัยที่ใหญ่ที่สุดจุดหนึ่งของ backend นี้
ทั้งหมด ไม่ใช่รายละเอียดเล็กๆ ที่ควรมองข้าม

---

## 25. ตาราง `users` ไม่มี Row-Level Security + `username` unique แบบ global ไม่ใช่ต่อ tenant

**บริบท:** POST /auth/login รับแค่ `{username, password}` — ไม่มี tenant ตามกฎเดียวกับ
ข้อ 23/CLAUDE.md ที่ห้าม client ส่ง tenant มาเอง ต้องออกแบบให้ login หา tenant ของ
user ได้จาก username เพียงอย่างเดียว

**ตัวเลือกที่พิจารณา:**
- (a) `username` unique เฉพาะภายใน tenant เดียวกัน (เหมือนระบบทั่วไปที่ผูก user เข้ากับ
  org) แล้วให้ client ส่ง tenant มาด้วยตอน login
- (b) `username` unique แบบ global ทั้งระบบ (เหมือน email) ทำให้ lookup ด้วย username
  อย่างเดียวไม่กำกวม
- สำหรับ RLS: (c) เปิด RLS บน `users` เหมือนตารางอื่น (d) ไม่เปิด RLS เลย

**สิ่งที่เลือก:** (b) + (d)

**เหตุผล:** (a) ต้องให้ client ส่ง tenant มาตอน login ซึ่งขัดกับกฎ "tenant ต้องมาจาก
JWT claim/server เท่านั้น" ตรงๆ — ตอน login ยังไม่มี JWT ให้อ่านด้วยซ้ำ จึงเหลือแค่ (b)
ที่ทำให้ lookup ด้วย username เพียงอย่างเดียวไม่กำกวม สำหรับ RLS: ทุกตารางอื่นที่มี RLS
(policy `tenant_isolation`) ต้องรู้ `app.tenant` ก่อน query เสมอ (fail-closed ตาม #7)
แต่ query login เกิด*ก่อน*รู้ว่าใครเป็นใครด้วยซ้ำ — ถ้าเปิด RLS บน users ด้วย policy
เดียวกัน login จะได้ 0 แถวเสมอเพราะ `app.tenant` ยังไม่เคยถูก set เลย ณ จุดนั้น จึงต้อง
ไม่เปิด RLS บนตารางนี้ และปฏิบัติกับมันเป็น "ตาราง auth ภายใน" แยกออกจากโมเดล
tenant-isolated ของ event data — ไม่มี endpoint ใดใน session นี้ query users นอกจาก
login path เดียว (ไม่มี `GET /users`)

**ข้อเสียที่ยอมรับ:** สอง tenant ตั้งชื่อ user ซ้ำกันตรงๆ ไม่ได้ (เช่นทั้งคู่อยากได้
username `alice`) — ยอมรับได้สำหรับ demo และในระบบจริงมักใช้ email เป็น username
อยู่แล้วซึ่ง unique ทั่วโลกโดยธรรมชาติ และถ้า session ในอนาคตเพิ่ม endpoint จัดการ
users (list/edit) จะต้องเพิ่มการกรอง tenant เองในโค้ด application ตรงๆ เพราะ RLS
จะไม่ช่วยอัตโนมัติเหมือนตารางอื่น

---

## 26. Password hashing: package `bcrypt` ตรงๆ แทน `passlib` หรือ `argon2`

**บริบท:** ต้องเลือกวิธี hash รหัสผ่านที่เก็บในคอลัมน์ `users.password_hash`

**ตัวเลือกที่พิจารณา:**
- (a) `passlib` (wrapper รอบ backend หลายแบบ รวม bcrypt) เคยเป็นตัวเลือกยอดนิยม
- (b) package `bcrypt` ตรงๆ (ไม่ผ่าน wrapper)
- (c) `argon2` (ผู้ชนะ Password Hashing Competition)

**สิ่งที่เลือก:** (b)

**เหตุผล:** `passlib` แทบไม่มีการดูแล (maintain) มาตั้งแต่ปี 2020 และมีปัญหา
compatibility ที่รู้กันแล้วกับ `bcrypt>=4.1` (กลไก detect เวอร์ชันของ passlib error
ออกมาตรงๆ) — การพึ่งพา wrapper ที่ไม่มีคนดูแลรอบ library ตัวเดียวกับที่จะใช้อยู่แล้ว
เพิ่มความเสี่ยงโดยไม่ได้อะไรเพิ่มเลย จึงตัด (a) ทิ้ง `argon2` แข็งแรงกว่าในทางทฤษฎีจริง
แต่ `bcrypt` เป็นค่ามาตรฐานที่อธิบายในวิดีโอเดโม 30 นาทีได้ง่ายกว่า และไม่มีข้อกังวล
เรื่อง native build เพิ่มเติมนอกเหนือจากที่ต้องมีอยู่แล้ว `bcrypt` เองก็ปรับ cost factor
ได้ (adaptive) ซึ่งเป็นคุณสมบัติสำคัญที่ต้องมีอยู่แล้วสำหรับการป้องกัน brute-force แบบ
offline ผลลัพธ์ของ `bcrypt.hashpw` เก็บ salt และ cost factor ไว้ในสตริงเดียวกันแล้ว
จึงไม่ต้องมีคอลัมน์ salt แยก

**ข้อเสียที่ยอมรับ:** ไม่ได้ใช้ algorithm ที่แข็งแรงที่สุดเท่าที่มี (argon2) — ยอมรับได้
เพราะ bcrypt ยังถือเป็นมาตรฐานที่ยอมรับกันกว้างขวางและไม่ใช่จุดอ่อนที่แท้จริงของระบบนี้
เมื่อเทียบกับความเสี่ยงอื่น (เช่นข้อ 24)

---

## 27. JWT: `PyJWT` + `HS256` + `HTTPBearer` แทน `python-jose` / `RS256` / `OAuth2PasswordBearer`

**บริบท:** ต้องเลือก library และรูปแบบการออก/ตรวจ JWT (claims: `sub`, `role`, `tenant`
ตามที่ CLAUDE.md ล็อกไว้)

**ตัวเลือกที่พิจารณา:**
- library: (a) `python-jose` (b) `PyJWT`
- algorithm: (a) `RS256` (asymmetric) (b) `HS256` (symmetric)
- transport: (a) `OAuth2PasswordBearer` (b) `HTTPBearer`

**สิ่งที่เลือก:** `PyJWT` + `HS256` + `HTTPBearer`

**เหตุผล:** `PyJWT` มี API ที่เล็กและตรงกับสิ่งที่ต้องใช้ (encode/decode) พอดี ได้รับการ
ดูแลต่อเนื่อง `RS256` (asymmetric) คุ้มค่าก็ต่อเมื่อมีหลายบริการที่ต้องตรวจ token ได้เอง
โดยไม่แชร์ secret กัน — ที่นี่มี backend เดียวที่ทั้งออกและตรวจ token เอง การแชร์ secret
เดียวกัน (`HS256`) จึงง่ายกว่าโดยไม่มีข้อเสียด้านความปลอดภัยในสถาปัตยกรรมนี้ ส่วน
`OAuth2PasswordBearer` ของ FastAPI สื่อว่า login เป็น OAuth2 password-grant แบบ
form-encoded (`application/x-www-form-urlencoded`) ซึ่งไม่ตรงกับที่ implement จริง
(`POST /auth/login` รับ JSON ธรรมดา) — `HTTPBearer` สะท้อนสิ่งที่ implement จริงตรงกว่า
ไม่บอกเป็นนัยว่ามี OAuth2 flow ที่ไม่มีอยู่จริง

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียเชิง security ที่มีนัยสำคัญในสถาปัตยกรรมปัจจุบัน
(backend เดียว) — ถ้าในอนาคตแยกเป็นหลาย service ที่ต้องตรวจ token โดยไม่แชร์ secret กัน
จะต้องย้ายไป `RS256` ตอนนั้น

---

## 28. `JWT_SECRET_KEY` ต้องทำให้ backend สตาร์ทไม่ขึ้นตอน import ถ้ายังเป็นค่า placeholder หรือไม่ได้ตั้งค่า

**บริบท:** `.env.example` ถูก commit ขึ้น repo (นั่นคือจุดประสงค์ของมัน) ค่า placeholder
ใดๆ ในไฟล์นี้จึงเป็นค่าสาธารณะที่ใครก็อ่านได้ ต้องป้องกันไม่ให้ deployment จริงรันด้วย
ค่านี้โดยไม่ตั้งใจ

**ตัวเลือกที่พิจารณา:**
- (a) ตรวจสอบ `JWT_SECRET_KEY` แบบ lazy — error ตอนแรกที่มีการ encode/decode token
- (b) ตรวจสอบตอน import module (`backend/config.py`) — error ทันทีตอน backend เริ่ม
  สตาร์ท ก่อนรับ request ใดๆ

**สิ่งที่เลือก:** (b)

**เหตุผล:** ถ้าเป็น (a) backend ที่ misconfigured จะรันขึ้นมาได้ปกติ ดูเหมือนใช้งานได้
จนกว่าจะมี request แรกที่ต้อง encode/decode token — ระหว่างนั้นอาจมี traffic เข้ามาแล้ว
โดยไม่มีใครรู้ว่า secret ยังเป็นค่า public เมื่อ deployment ที่ใช้ค่า placeholder จริง
จะทำให้ใครก็ปลอม JWT ของ tenant ไหนก็ได้ที่ signature ผ่าน (เพราะ secret เป็นค่า
สาธารณะ) ซึ่งทำให้ RLS ทั้งระบบไร้ความหมายในทางปฏิบัติ (ห่วงโซ่ความปลอดภัยทั้งหมดพังที่
จุดเริ่มต้น — ดูข้อ 23 กับ #6-#8) การ fail ทันทีตอน import ทำให้ deployment ที่
misconfigured ไม่รับ request แม้แต่ตัวเดียว แทนที่จะทำงาน "ดูปกติ" ไปพักหนึ่งก่อน
ฟังก์ชันตรวจสอบ (`validate_jwt_secret`) แยกเป็นฟังก์ชันเดี่ยวๆ ไม่ใช่โค้ดลอยตัวระดับ
module เพื่อให้ test เรียกมันตรงๆ ด้วยค่า input ต่างๆ ได้โดยไม่ต้องใช้
`importlib.reload`

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียเชิง behavior ที่มีนัยสำคัญ — เป็นการ fail เร็วขึ้น
เท่านั้น อาจทำให้ผู้ตรวจที่ลืม copy `.env.example` เป็น `.env` (หรือลืมตั้ง
`JWT_SECRET_KEY` ใหม่) เจอ error ทันทีตอน `make up`/สตาร์ท backend ซึ่งถือเป็น
พฤติกรรมที่ตั้งใจ ไม่ใช่บั๊ก

---

## 29. POST /auth/login รัน bcrypt verify กับ dummy hash เสมอ เมื่อไม่เจอ username (ป้องกัน timing side-channel)

**บริบท:** `POST /auth/login` ตามธรรมชาติจะตอบเร็วกว่าเมื่อไม่เจอ username เลย
(return 401 ทันที ไม่มีการเรียก bcrypt) เทียบกับกรณีเจอ username แต่รหัสผ่านผิด
(ต้องรัน bcrypt verify ซึ่งช้าโดยตั้งใจ) — ผู้โจมตีที่วัดเวลาตอบสนองสามารถแยกสองกรณีนี้
ออกจากกันได้ และไล่เดา (enumerate) ว่า username ไหนมีอยู่จริงในระบบ โดยไม่ต้องเดา
รหัสผ่านเลยด้วยซ้ำ

**ตัวเลือกที่พิจารณา:**
- (a) ปล่อยตามธรรมชาติ — ไม่เจอ username ตอบทันที เจอแต่รหัสผิดตอบช้ากว่า
- (b) เมื่อไม่เจอ username ให้รัน `verify_password` กับ bcrypt hash คงที่ (dummy)
  ก่อน return 401 เสมอ

**สิ่งที่เลือก:** (b)

**เหตุผล:** การรัน bcrypt กับ dummy hash ทำให้ทั้งสอง code path (เจอ/ไม่เจอ username)
เสียเวลา bcrypt เท่าๆ กันเสมอ ทำให้เวลาตอบสนองไม่สัมพันธ์กับว่า username นั้นมีอยู่จริง
หรือไม่อีกต่อไป — เป็นการลด information leak ที่ต้นทุนต่ำมาก (เพิ่มแค่ bcrypt call
เดียวในกรณีที่ไม่เจอ user)

**ข้อเสียที่ยอมรับ:** เป็นการบรรเทา ไม่ใช่การรับประกันแบบ constant-time ที่สมบูรณ์ —
jitter ของ network, cache effect, และปัจจัยอื่นๆ ยังทำให้เวลามีความต่างเล็กน้อยได้ใน
ทางปฏิบัติ ยอมรับได้สำหรับ threat model ของ demo นี้ ไม่ใช่การพิสูจน์ทางคณิตศาสตร์ว่า
constant-time จริง

---

## 30. Connection pool (`psycopg_pool.AsyncConnectionPool`) + `set_config` ต่อ request — transaction เปิดค้างตลอดอายุ request โดยตั้งใจ

**บริบท:** `ingest/db.py` เปิด connection เดียวค้างไว้ต่อ process (listener หนึ่งตัว =
tenant เดียวตลอดอายุ process) แต่ backend รับ concurrent request จากหลาย tenant
พร้อมกันในกระบวนการเดียว จึงต้องมี connection pool และต้องออกแบบให้
`set_config('app.tenant', ..., true)` (แบบ `is_local` เดียวกับ #18) ทำงานถูกต้องโดยไม่
รั่ว tenant ข้าม request ที่ใช้ connection เดียวกันซ้ำจาก pool

**ตัวเลือกที่พิจารณา:**
- library pool: (a) เปิด connection ใหม่ทุก request (ไม่ pool เลย) (b)
  `psycopg_pool.AsyncConnectionPool`
- อายุ transaction ใน dependency `get_tenant_conn`: (c) ปิด transaction ทันทีหลัง
  `set_config` แล้วเปิด transaction ใหม่สำหรับ query จริง (d) เปิด transaction เดียว
  คลุมตั้งแต่ `set_config` ไปจนจบ request ทั้งหมด

**สิ่งที่เลือก:** (b) + (d)

**เหตุผล:** (a) เปิด connection ใหม่ทุก request มีต้นทุน TCP handshake + auth ต่อ
request ซึ่งไม่จำเป็นเมื่อมี pool ให้ใช้อยู่แล้ว และ `psycopg_pool` เป็น companion
package ของ `psycopg` (driver ที่เลือกไว้แล้วตั้งแต่ #15) ออกแบบมาสำหรับ async +
FastAPI พอดี จึงไม่ได้เพิ่ม dependency family ใหม่ สำหรับ (c) ใช้ไม่ได้จริง:
`set_config(..., true)` คือ `is_local` ซึ่งมีผลแค่ในทรานแซกชันที่มันถูกเรียก — ถ้าปิด
ทรานแซกชันทันทีหลัง `set_config` แล้วเปิดใหม่สำหรับ query จริง ค่า `app.tenant` จะ
reset กลับไปเป็น `''` ก่อน query จะได้รันด้วยซ้ำ (ตาม #18-#19) ดังนั้น `set_config`
กับทุก query ที่ต้องพึ่งมันต้องอยู่ในทรานแซกชันเดียวกันเสมอ — วิธีเดียวที่ทำแบบนี้ได้
กับ dependency แบบ `yield` ของ FastAPI คือให้ transaction เปิดคลุมตลอดอายุของ
dependency (คือตลอด request) ความปลอดภัยจาก tenant leak มาจากสองอย่างรวมกัน:
(1) `pool.connection()` ให้สิทธิ์ผูกขาด (exclusive) การใช้ connection นั้นตลอด
request เดียว ไม่มีสอง request ใช้ connection เดียวกันพร้อมกัน (2) ทุก request ที่
ผ่าน dependency นี้ set tenant ของตัวเองเป็นคำสั่งแรกในทรานแซกชันของตัวเองเสมอ
ไม่เคยพึ่งพาค่าที่ request ก่อนหน้าทิ้งไว้

**ข้อเสียที่ยอมรับ:** connection ที่ถูก checkout จะถูกยึดครองตลอดอายุ request ทั้งหมด
ไม่ใช่แค่ช่วงเวลาที่ query จริงใช้ — request ที่ช้า (เช่น `/search` ที่ query กว้าง หรือ
client ที่รับ response ช้า) จะกิน connection จาก pool นานกว่าที่ query เพียวๆ ต้องใช้
ถ้ามี traffic สูงพร้อมกันหลาย request ช้าๆ pool อาจหมดเร็วกว่าที่ latency ของ query
อย่างเดียวควรจะบ่งบอก บรรเทาในทางปฏิบัติด้วยการจำกัดขนาดผลลัพธ์ (`_MAX_LIMIT` ใน
`/search` — ดูข้อ 31) ไม่ได้แก้ปัญหานี้อย่างสมบูรณ์ในเซสชันนี้ — ระบบที่ต้องรับ load
จริงอาจต้องพิจารณากลไกอื่นแทน เช่น session-level tenant หรือ `SET ROLE` แบบต่อ
statement

---

## 31. `/search` ใช้ OFFSET pagination + trick "ดึงเกิน 1 แถว" แทน `COUNT(*)` แยก และแทน keyset pagination

**บริบท:** ต้องออกแบบ pagination ของ `GET /search` บนตารางที่มีปริมาณข้อมูลสูงต่อเนื่อง
(`events`)

**ตัวเลือกที่พิจารณา:**
- การรู้ว่ามีหน้าถัดไปหรือไม่ (`has_more`): (a) query `COUNT(*)` แยกต่างหากด้วย
  เงื่อนไขเดียวกัน (b) ดึงมา `limit + 1` แถว แล้วดูว่าแถวที่ `limit+1` มีอยู่จริงไหม
- รูปแบบ pagination: (c) OFFSET/LIMIT ปกติ (d) keyset (cursor-based) pagination
  โดยใช้ `(event_time, id)` ของแถวสุดท้ายเป็น cursor

**สิ่งที่เลือก:** (b) + (c)

**เหตุผล:** (a) `COUNT(*)` บนตาราง log ที่มีปริมาณสูงเป็นการ scan ที่มีต้นทุนพอๆ กับ
(หรือมากกว่า) query ข้อมูลจริงเอง แลกกับข้อมูลที่ endpoint นี้ไม่ได้ต้องการ (แค่รู้ว่า
"มีต่อไหม" ไม่ต้องรู้จำนวนทั้งหมดเป๊ะๆ) — การดึงเกินมา 1 แถวแล้วตัดทิ้งถ้าเกิน `limit`
ให้คำตอบเดียวกัน (มีต่อ/ไม่มีต่อ) แทบไม่มีต้นทุนเพิ่มเทียบกับ query ปกติเลย สำหรับ
(c) vs (d): OFFSET ช้าลงเมื่อ offset สูงขึ้นเรื่อยๆ เพราะ Postgres ต้องอ่านแล้วทิ้ง
ทุกแถวก่อนหน้า offset นั้นก่อนถึงจะเริ่มนับแถวที่ต้องการจริง — keyset pagination
(ใช้ `(event_time, id)` ของแถวสุดท้ายที่เห็นเป็น cursor แทนเลข offset) ใช้ index ได้
เต็มที่ไม่ว่าจะลึกแค่ไหน ไม่มีปัญหานี้เลย แต่ (c) ถูกเลือกเพราะเข้าใจและอธิบายง่ายกว่า
มาก (`?limit=50&offset=100` ตรงไปตรงมา เทียบกับต้อง encode/decode cursor object)
และที่ `_MAX_LIMIT = 500` ผลรวมกับปริมาณข้อมูลระดับ demo ทำให้ offset ที่ลึกจริงๆ
ไม่เคยเกิดขึ้นในทางปฏิบัติของ session นี้

**ข้อเสียที่ยอมรับ:** ถ้าข้อมูลโตขึ้นมากในอนาคต (production scale จริง) การเข้าหน้า
ลึกๆ ด้วย OFFSET จะช้าลงเรื่อยๆ ต่างจาก keyset ที่คงที่ไม่ว่าจะลึกแค่ไหน — ยอมรับได้
สำหรับ demo/assignment นี้ แต่เป็นจุดที่ต้องทบทวนใหม่ถ้าเอาไปใช้งานจริงกับข้อมูล
ปริมาณสูงต่อเนื่องในระยะยาว

---

## 32. ไม่มี token revocation/blocklist — JWT แบบ stateless มีข้อแลกเปลี่ยนเรื่อง credential ที่เพิกถอนไม่ได้ทันที

**บริบท:** JWT ที่ออกไปแล้วมีอายุจนถึง `exp` เสมอ เพราะ backend ไม่เช็คกับ DB ทุก
request (นั่นคือข้อดีหลักของ stateless JWT — ไม่ต้อง round-trip ไป DB เพื่อตรวจทุก
request) แต่นั่นหมายความว่าถ้าบัญชีถูกลบ หรือเปลี่ยน role ระหว่างที่ token ยังไม่หมด
อายุ token เดิมยังใช้งานได้ต่อไปจนถึง `exp` เดิม เพราะไม่มีจุดใดเช็คสถานะบัญชีปัจจุบัน
กับ DB อีกเลยหลัง login

**ตัวเลือกที่พิจารณา:**
- (a) เพิ่ม token blocklist (เก็บ token/jti ที่ถูกเพิกถอนไว้ใน DB หรือ cache แยก
  เช็คทุก request)
- (b) ใช้ refresh token อายุสั้นคู่กับ access token อายุสั้นกว่าเดิมมาก (ลด window
  ที่ token เก่ายังใช้ได้)
- (c) ไม่ทำอะไรเพิ่ม ปล่อยให้ `JWT_EXPIRE_MINUTES` (ตั้งไว้ 60 นาที) เป็นขอบเขตบนของ
  ความเสี่ยงนี้

**สิ่งที่เลือก:** (c)

**เหตุผล:** ทั้ง (a) และ (b) ทำให้ JWT ไม่ใช่ stateless อีกต่อไปในทางปฏิบัติ (ต้องมี
state เพิ่มที่ต้องเช็คทุก request หรือทุกครั้งที่ refresh) ซึ่งเพิ่มความซับซ้อนที่ไม่มี
requirement รองรับใน session นี้ — ไม่มี endpoint จัดการผู้ใช้ใดๆ เลย (ไม่มี delete
user, ไม่มี change role) ที่จะทำให้ปัญหานี้เกิดขึ้นจริงได้ในทางปฏิบัติของ session นี้
และ `JWT_EXPIRE_MINUTES=60` ทำให้ window ของความเสี่ยงมีขอบเขตชัดเจนและสั้นพอสำหรับ
demo

**ข้อเสียที่ยอมรับ:** ถ้า session ในอนาคตเพิ่ม endpoint ลบ/แก้ไขผู้ใช้ ต้องกลับมา
พิจารณาเรื่องนี้ใหม่ทันที เพราะ ณ ตอนนั้น "บัญชีถูกลบแต่ token ยังใช้ได้อีกจนถึง 60
นาที" จะกลายเป็นสถานการณ์จริงที่เกิดขึ้นได้ ไม่ใช่แค่สมมติฐานทางทฤษฎีอีกต่อไป

---

## 33. Docker: รัน backend container ด้วย non-root user

**บริบท:** `python:3.10-slim` (base image ของ `backend/Dockerfile`) รัน process เป็น
root โดย default ถ้าไม่ระบุ `USER` เอง

**ตัวเลือกที่พิจารณา:** (a) ปล่อยรันเป็น root ตาม default ของ base image (b) สร้าง
user ที่ไม่มีสิทธิ์พิเศษ (`useradd` + `USER`) แล้วรัน backend ด้วย user นั้น

**สิ่งที่เลือก:** (b)

**เหตุผล:** ถ้า FastAPI app มีช่องโหว่ระดับ application (เช่น dependency ที่มีช่องโหว่
หรือบั๊กที่ยอมให้ execute คำสั่งได้) การรันเป็น root หมายความว่าผู้โจมตีจะได้สิทธิ์ root
ภายใน container ทันที ซึ่งเปิดโอกาสให้ทำอะไรกับ filesystem/process table ของ
container ได้กว้างกว่าที่ควร การรันด้วย user ที่ไม่มีสิทธิ์พิเศษจำกัดขอบเขตความเสียหาย
นี้ (แม้จะไม่ช่วยเรื่อง container-escape ซึ่งเป็นเรื่องของ container runtime/kernel
ไม่ใช่สิ่งที่ Dockerfile ควบคุมได้) นี่คือตัวอย่างที่จับต้องได้ของหัวข้อ "hardening"
ที่อยู่ใน bonus points ของโจทย์ (§8 bonus)

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียเชิง behavior ที่มีนัยสำคัญสำหรับ backend นี้ (ไม่ได้
bind port ต่ำกว่า 1024 หรือต้องเขียนไฟล์ระดับ system ใดๆ ที่ต้องใช้สิทธิ์ root) —
เพิ่มบรรทัดเดียวใน Dockerfile แลกกับความปลอดภัยที่ดีขึ้นชัดเจน

---

## 34. `GET /health` ไม่ต้อง auth และตอบข้อมูลขั้นต่ำที่สุด

**บริบท:** docker-compose healthcheck ของ service `backend` และ load balancer/uptime
check ตอน deploy ขึ้น SaaS/cloud ต้องมีทางเช็คว่า backend process ยังเชื่อมต่อ DB
ได้อยู่ โดยไม่ต้อง authenticate ก่อน (healthcheck ทั่วไปไม่ถือ credential)

**ตัวเลือกที่พิจารณา:**
- (a) endpoint เดียวกันนี้ต้อง auth เหมือน endpoint อื่นทั้งหมด
- (b) ไม่ต้อง auth แต่จำกัดสิ่งที่ตอบกลับให้น้อยที่สุด (แค่ "เชื่อมต่อ DB ได้ไหม")
  ไม่บอกเวอร์ชัน Postgres, connection string, หรือรายละเอียด exception ใดๆ

**สิ่งที่เลือก:** (b)

**เหตุผล:** เครื่องมือ healthcheck (docker-compose, cloud load balancer) ไม่ถือ JWT
และไม่ควรต้องถือ — endpoint นี้จึงต้องเปิดแบบไม่ auth โดยธรรมชาติของการใช้งาน แต่การ
ไม่ auth หมายความว่าใครก็เรียกได้ ดังนั้นสิ่งที่ตอบกลับต้องไม่รั่วข้อมูลที่มีประโยชน์กับ
ผู้โจมตี (เวอร์ชัน Postgres ช่วยเลือก exploit ที่ตรงเวอร์ชัน, connection string
เปิดเผยโครงสร้าง network ภายใน) — ตอบแค่ `{"status": "ok", "database": "ok"}` หรือ
503 เมื่อต่อ DB ไม่ได้ พร้อม detail แบบทั่วไป ("database unreachable") ไม่ใช่ข้อความ
exception ดิบ

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียเชิง security ที่มีนัยสำคัญ — endpoint นี้ตอบ 503
(ไม่ใช่ 200 พร้อม field บอกสถานะ) เมื่อ DB ไม่พร้อม เพื่อให้ healthcheck แบบ
`curl -f`/similar ที่เช็คแค่ HTTP status ทำงานถูกต้องด้วย

---

## 35. `alert_rules` + `alerts`: RLS แบบเดียวกับ `events`, ไม่ partition, และ composite FK `(tenant, rule_id)`

**บริบท:** session นี้เพิ่ม alerting — ต้องมีตารางเก็บ config ของ alert rule
(admin แก้ได้ viewer ดูได้อย่างเดียว) และตารางเก็บ alert ที่ยิงแล้ว (ทั้งสอง role
ดูได้) โดยข้อมูลทั้งสองเป็นข้อมูลต่อ tenant เหมือน `events`

**ตัวเลือกที่พิจารณา:**
- RLS: (a) เปิด RLS เหมือน `events` (b) ไม่เปิด แล้วพึ่ง `WHERE tenant = ?`
  ในโค้ด backend เอง
- Partitioning: (c) partition รายวันเหมือน `events` (d) ตารางธรรมดา ไม่ partition
- ความสัมพันธ์ `alerts.rule_id` → `alert_rules.id`: (e) FK ปกติ `rule_id
  REFERENCES alert_rules(id)` (f) composite FK `(tenant, rule_id) REFERENCES
  alert_rules(tenant, id)` (ต้องมี `UNIQUE (tenant, id)` บน `alert_rules` เพิ่ม)

**สิ่งที่เลือก:** (a) + (d) + (f)

**เหตุผล:** (a) — หลักการเดียวกับ #6-#8: ทุก query ต้องผ่าน RLS จริง ไม่ใช่แค่
filter ในโค้ด ข้อมูล alert ของ tenant หนึ่งไม่ควรรั่วไปอีก tenant ด้วยเหตุผล
เดียวกับ `events` ทุกประการ — ทั้งสองตารางใช้ policy `tenant_isolation` รูปแบบ
เดียวกันเป๊ะ (`tenant = current_setting('app.tenant', true)`)

(d) — `events` ต้อง partition เพราะรับ insert ต่อเนื่องปริมาณสูงตลอดเวลา (log
ทุกรายการ) แต่ `alerts` ยิงน้อยกว่ามาก (ถูกจำกัดด้วย cooldown ต่อ src_ip อยู่แล้ว
ดู #36) และ `alert_rules` เป็นแค่ config ที่ admin แก้เป็นครั้งคราว ไม่มี pattern
เขียนต่อเนื่องปริมาณสูงแบบ `events` ที่จะทำให้ต้นทุนการ partition (#9-#11) คุ้มค่า

(f) — ถ้าใช้ FK ธรรมดาแบบ (e) ไม่มีอะไรบังคับว่า `alerts.tenant` กับ
`alert_rules.tenant` (ของ rule ที่ `rule_id` ชี้ไป) ต้องตรงกัน มันจะถูกต้องแค่
เพราะโค้ด engine เขียนถูกทุกครั้ง (query rule พร้อม tenant เดียวกันเสมอ) —
เป็นสมมติฐานแบบเดียวกับที่ #19-#20 เจอมาก่อนแล้วว่าไม่ควรพึ่งพาเฉยๆ composite FK
`(tenant, rule_id) REFERENCES alert_rules (tenant, id)` (ต้องมี
`UNIQUE (tenant, id)` เพิ่มบน `alert_rules` เพื่อให้ Postgres อ้างอิงได้) ทำให้
DB เองปฏิเสธการ insert ทันทีถ้า `alerts.tenant` ไม่ตรงกับ tenant ของ rule ที่ชี้ไป
ไม่ต้องพึ่งพาว่าโค้ด engine เขียนถูกเฉยๆ

**ข้อเสียที่ยอมรับ:** ไม่มี retention policy สำหรับ `alerts` ในเซสชันนี้ (ต่างจาก
`events` ที่โจทย์บังคับ ≥7 วัน) — ยอมรับได้เพราะไม่ใช่ requirement ที่ให้คะแนน
สำหรับตารางนี้ ถ้าปริมาณ alert โตมากในอนาคตต้องกลับมาพิจารณาใหม่ และ
`alert_rules` ไม่มี DELETE endpoint (ปิดด้วย `enabled=false` แทน) เพื่อเลี่ยงต้อง
ตัดสินใจว่า `alerts` ที่อ้างอิง rule ที่ถูกลบไปแล้วควรเกิดอะไรขึ้น

---

## 36. Detection window ของ alert engine ใช้ `ingested_at` ไม่ใช่ `event_time` — แต่รายงาน `event_time` ใน alert

**บริบท:** query ตรวจจับ "failed login ≥N ครั้งใน M วินาที" ต้องเลือกว่าจะกรอง
แถวด้วยคอลัมน์เวลาไหน `event_time` (เวลาที่อุปกรณ์ต้นทางอ้างเอง) หรือ
`ingested_at` (เวลาที่ระบบนี้ insert แถวจริงๆ, `DEFAULT now()`, มีอยู่แล้วตั้งแต่
session แรก)

**ตัวเลือกที่พิจารณา:**
- (a) ใช้ `event_time` อย่างเดียวทั้งกรองและรายงาน
- (b) ใช้ `ingested_at` อย่างเดียวทั้งกรองและรายงาน
- (c) กรอง (WHERE) ด้วย `ingested_at` แต่รายงาน `window_start`/`window_end`
  ในตาราง `alerts` ด้วย `MIN`/`MAX(event_time)` ของแถวที่ match

**สิ่งที่เลือก:** (c)

**เหตุผล:** (a) ถูกต้องในแง่ความหมาย ("เหตุการณ์เกิดขึ้นจริงเมื่อไหร่") แต่เอามาใช้
เป็นเงื่อนไข WHERE ตรงๆ ทำให้ความถูกต้องของ alert ขึ้นอยู่กับนาฬิกาของอุปกรณ์ที่
ระบบนี้ไม่ได้ควบคุม — ถ้านาฬิกาอุปกรณ์ช้ากว่าจริงเกิน `window_seconds`
เหตุการณ์ทุกอันจากอุปกรณ์นั้นจะมี `event_time` อยู่นอกหน้าต่างเสมอ ไม่ใช่แค่ครั้ง
เดียว แต่ **ตลอดไปจนกว่าจะมีคนไปแก้นาฬิกา** — เป็น false negative แบบเงียบและ
ถาวร เช่นเดียวกับ agent ที่ buffer แล้วส่ง log เป็น batch ทุก 2-3 นาที ก็เจอปัญหา
เดียวกันถ้า delay มากกว่า window — เป็น failure mode แบบเดียวกับที่ #7/#20
พยายามเลี่ยงมาตลอด (พึ่งพา input จากภายนอกที่ตรวจสอบไม่ได้)

(b) แก้ปัญหานาฬิกาได้เต็มที่ (ใช้เวลาของระบบเราเองเท่านั้น) แต่ถ้าเอามารายงานด้วย
จะทำให้ `window_start`/`window_end` บอกว่า "เพิ่งเกิดขึ้น" สำหรับเหตุการณ์ที่จริงๆ
เกิดขึ้นเมื่อไหร่ก็ไม่รู้ตามที่อุปกรณ์อ้าง — ไม่มีประโยชน์กับคนที่ต้องสืบสวน incident
จริงๆ ว่าเกิดขึ้นช่วงไหน

(c) แยกสองหน้าที่ออกจากกัน: **การตัดสินใจว่าจะยิง alert หรือไม่** ใช้ `ingested_at`
(ไม่พึ่งนาฬิกาอุปกรณ์เลย ปลอดภัยกว่าในแง่ threat model ของระบบ log
management ที่ไม่ควรเชื่อ input จากอุปกรณ์ภายนอกแม้แต่เรื่อง timing ของตัวเอง)
ส่วน **สิ่งที่รายงานให้ผู้ดูแลเห็น** ใช้ `event_time` (`MIN`/`MAX` ของแถวที่ match
ในก query เดียวกัน ไม่มีต้นทุนเพิ่ม) เพื่อให้เห็นช่วงเวลาจริงตามที่อุปกรณ์อ้าง —
ได้ความถูกต้องทั้งสองด้านพร้อมกัน

**ข้อเสียที่ยอมรับ:** สืบทอดข้อเสียของ (b) มาเต็มๆ ในด้านการกรอง — ถ้าอุปกรณ์
หลุดการเชื่อมต่อแล้วส่ง log ที่สะสมไว้ 20 นาทีมาในครั้งเดียว (`ingested_at`
กระจุกตัวในไม่กี่วินาที) ระบบจะเห็นเป็น burst ที่เกิดในเวลาสั้นๆ ทั้งที่จริงกระจาย
อยู่ 20 นาที เป็น false positive ที่เป็นไปได้ — เช่นเดียวกับการโหลด batch ข้อมูล
เก่าผ่าน `ingest/batch_loader.py` โดยไม่ใส่ `--rebase-timestamps` ถ้าไฟล์นั้น
มีแถวที่ตรงเงื่อนไข ≥ threshold ต่อ src_ip เดียวกัน จะดูเหมือน burst ที่เพิ่งเกิด
ทั้งที่เป็นข้อมูลเก่า (ยอมรับได้เพราะตัวอย่างในโปรเจคนี้ไม่มีไฟล์ไหนมีแถวมากพอจะ
ชนเงื่อนไข default `threshold=5`) — เพิ่ม index `idx_events_tenant_ingested_at`
(`02_schema.sql`) เพราะ index เดิม 4 ตัวของ `events` (#12) ไม่มีตัวไหนมี
`ingested_at` เลย ถ้าไม่เพิ่ม query นี้ (รันทุก 30 วินาทีตลอดไป) จะช้าลงเรื่อยๆ
ตามปริมาณข้อมูลใน retention window — เป็นต้นทุน index บน insert เพิ่มอีกหนึ่งตัว
ตามหลักการเดียวกับที่ #12 ใช้เลือก/ตัด index ของ `events`
(หมายเหตุ: ทำให้เหตุผลของ `idx_events_tenant_src_ip_time` ใน #12 ที่อ้างอิง
"the required alert rule" ตอนนี้ใช้ได้แค่กับ Top-IP บน dashboard เท่านั้น
ไม่ใช่กับ query ของ alert engine เองอีกต่อไป เพราะ query นั้นเปลี่ยนมากรองด้วย
`ingested_at` ไม่ใช่ `event_time`)

---

## 37. Alert engine เป็น scheduled poll ทุก 30 วินาที ไม่ใช่ streaming/trigger

**บริบท:** ต้องตัดสินใจว่ากลไกตรวจจับ "failed login ≥5 ครั้งใน 5 นาที" จะทำงาน
แบบไหน — ตรวจทันทีเมื่อมี event ใหม่เข้ามา (streaming) หรือตรวจเป็นรอบ

**ตัวเลือกที่พิจารณา:**
- (a) DB trigger บน `events` ที่ยิง `pg_notify` แล้วมี listener process แยก
- (b) message queue/streaming pipeline (เช่น รูปแบบ Kafka)
- (c) scheduled poll: process เดียว `while True: evaluate(); sleep(30)`
  รัน SQL ธรรมดาทุกรอบ

**สิ่งที่เลือก:** (c)

**เหตุผล:** เงื่อนไขของ rule เองมีหน่วยเป็นนาที (5 ครั้งใน 5 นาที) — การตรวจจับ
ที่ไวกว่านั้นมาก (ภายใน 1 วินาทีหลัง event ที่ 5) แทบไม่ต่างจากตรวจภายใน 30
วินาทีในทางปฏิบัติ ไม่คุ้มกับความซับซ้อนที่เพิ่มขึ้น (a) ผูก alert evaluation
เข้ากับความสำเร็จของ insert เอง (ถ้า trigger error จะกระทบ insert ที่มันติดอยู่
ด้วย) — เป็น failure mode แบบเดียวกับที่ #6/#9/#11 ปฏิเสธมาตลอดสำหรับ write
path (b) เป็น infrastructure ใหม่ที่ไม่มีอะไรในโปรเจคนี้รองรับอยู่แล้ว ขัดกับกฎ
ข้อ 2 ของ `CLAUDE.md` (ต้องอธิบาย library/pattern ใหม่ก่อนใช้ และ "อาจ scale
ในอนาคต" ไม่ใช่เหตุผลที่พอสำหรับ demo) — เป็น trade-off แบบเดียวกับที่ #31
เลือก OFFSET pagination เหนือ keyset ที่ demo scale นี้

**ข้อเสียที่ยอมรับ:** ตรวจจับช้าสุด ~30 วินาทีหลังเงื่อนไขเป็นจริง (ไม่ใช่ real-time
เป๊ะ) — ยอมรับได้เพราะ window ของ rule เองกว้างกว่านี้มาก และ process เดียว
ที่ evaluate ทุก tenant ตามลำดับ (ไม่ parallel) หมายความว่าถ้ามี tenant จำนวน
มากมาก การ evaluate รอบหนึ่งอาจใช้เวลานานกว่า interval เอง — ยังไม่ implement
การจำกัด/ขนาน tenant ในเซสชันนี้ เพราะจำนวน tenant ระดับ demo ไม่ถึงจุดนั้น

---

## 38. Cooldown คีย์ด้วย `(tenant, rule_id, src_ip)` และคำนวณผ่าน `alerts.triggered_at` เอง ไม่มีตารางแยก

**บริบท:** query ตรวจจับเป็น rolling window ที่รันซ้ำทุก 30 วินาที — ถ้า src_ip
หนึ่งยังโจมตีต่อเนื่อง มันจะ match เงื่อนไข "≥5 ครั้งใน 5 นาที" ซ้ำทุกรอบตราบใด
ที่การโจมตียังไม่หยุด ถ้าไม่มี cooldown จะยิง alert (และ webhook) ทุก 30 วินาที
สำหรับเหตุการณ์เดียวกัน

**ตัวเลือกที่พิจารณา:**
- คีย์ของ cooldown: (a) global ทั้ง tenant (b) ต่อ `(tenant, rule_id, src_ip)`
- แหล่งข้อมูล cooldown: (c) query `MAX(triggered_at)` จาก `alerts` เอง
  (d) ตารางแยก `cooldown_state` เก็บเวลาล่าสุดต่อคีย์
- พฤติกรรมเมื่อ cooldown หมดอายุแต่การโจมตียังไม่หยุด: (e) หยุดแจ้งเตือนถาวร
  หลังครั้งแรก (f) แจ้งเตือนซ้ำเมื่อ cooldown หมดอายุ ถ้าเงื่อนไขยังเป็นจริงอยู่

**สิ่งที่เลือก:** (b) + (c) + (f)

**เหตุผล:** (a) จะทำให้ IP ที่โจมตีจริงตัวที่สองถูกซ่อนไปเพราะ IP อื่นเพิ่งยิง
alert ไปก่อนหน้านี้ — ไม่มีเหตุผลรองรับเลย (b) ตัดปัญหานี้ทันทีเพราะคีย์แยกตาม
src_ip ที่แท้จริง (c) ไม่มีข้อมูลอะไรที่ตาราง `alerts` ที่มีอยู่แล้วไม่ได้ให้ —
สร้างตารางใหม่แค่เพื่อ derive ค่าเดียวกันคือความซับซ้อนที่ไม่จำเป็นตามกฎข้อ 3
ของ `CLAUDE.md` (e) คือ "เงียบระหว่างเหตุการณ์จริง" ซึ่งแย่กว่า spam เสียอีก —
ถ้า attacker โจมตีต่อเนื่อง 1 ชั่วโมง แต่ admin ได้ alert แค่ครั้งเดียว ก็ไม่รู้เลยว่า
ยังโจมตีต่ออยู่หรือหยุดไปแล้ว (f) ทำให้ attacker ที่ยังโจมตีต่อเนื่องได้รับการแจ้งเตือน
ซ้ำเป็นระยะ (ทุก `cooldown_seconds`, default 15 นาที) แทนที่จะเป็น "ครั้งเดียว
ตลอดกาล" หรือ "ทุก 30 วินาที" — จุดกึ่งกลางที่ไม่พลาด incident จริงและไม่ spam
`cooldown_seconds` เป็นคอลัมน์แยกจาก `window_seconds` โดยตั้งใจ (ไม่ผูกเป็นค่า
เดียวกัน) เพราะ "ตรวจจับนานแค่ไหน" กับ "แจ้งเตือนซ้ำถี่แค่ไหน" ควรเป็นคนละ knob

**ข้อเสียที่ยอมรับ:** ออกแบบมาเพื่อ engine instance เดียว (single process) —
ถ้ามีหลาย instance รันพร้อมกันในอนาคต (เช่น scale ออก) การเช็ค cooldown แบบนี้
มี race condition (สอง instance เห็น "past cooldown" พร้อมกันแล้วยิงซ้ำ) —
ยอมรับได้เพราะ session นี้ deploy แค่ instance เดียวเสมอ (`docker-compose.yml`
ไม่มี replica) ถ้าต้อง scale ในอนาคตต้องเพิ่ม distributed lock หรือทำให้ insert
เป็น idempotent ด้วยกลไกอื่น

---

## 39. Failed-login matching heuristic: `event_type`/`action ILIKE` แทน enum ตายตัว

**บริบท:** query ตรวจจับต้องรู้ว่าแถวไหนคือ "failed login" แต่แต่ละ source
normalize คำนี้ไม่เหมือนกันเลย — `ad` → `event_type="LogonFailed"`, `api` →
`event_type="app_login_failed"` — ไม่มีคอลัมน์ boolean หรือค่า `action` กลาง
ที่ใช้ร่วมกันได้แบบ `severity`/`src_ip`

**ตัวเลือกที่พิจารณา:**
- (a) allowlist ค่า `event_type` ที่รู้จักตรงๆ ทีละ source (เช่น
  `event_type IN ('LogonFailed', 'app_login_failed', ...)`)
- (b) `(event_type ILIKE '%login%' OR event_type ILIKE '%logon%') AND
  (event_type ILIKE '%fail%' OR action ILIKE '%fail%')`

**สิ่งที่เลือก:** (b)

**เหตุผล:** (a) ต้องแก้โค้ด engine ทุกครั้งที่มี source ใหม่เพิ่มเข้ามา และไม่รู้
ล่วงหน้าว่า source ในอนาคตจะตั้งชื่อ event_type ว่าอะไร — (b) จับทั้งสอง
ตัวอย่างที่มีอยู่จริงในโปรเจคนี้ได้โดยไม่ต้องรู้จักชื่อ source ล่วงหน้าเลย การบังคับ
ทั้งคำว่า "login/logon" และ "fail" ร่วมกัน (ไม่ใช้แค่ "fail" อย่างเดียว) ป้องกันไม่ให้
จับ event_type ที่ไม่เกี่ยวข้องแต่มีคำว่า fail ปนอยู่ (เช่น สมมติ source อื่นใช้
`task_failed`)

**ข้อเสียที่ยอมรับ:** source ในอนาคตที่ normalize "failed login" เป็นค่าที่ไม่มี
คำว่า login/logon/fail เลย (เช่น รหัสตัวเลขล้วนไม่มีข้อความ) จะไม่ถูกจับ — เป็น
gap จริงแต่ไม่กระทบ session นี้เพราะ normalizer ทุกตัวที่มีอยู่แล้วผลิตข้อความที่
match ทั้งหมด เหมือนกับที่ #3 ยอมรับว่าไม่บังคับ enum บน `action` ด้วยเหตุผล
คล้ายกัน (ข้อมูลจริงจาก vendor ไม่ได้ fit enum ตายตัวเสมอไป)

---

## 40. Alert engine เป็น process แยก (`alerting/engine.py`) และหา tenant จาก `users`

**บริบท:** alert engine ต้องรันเป็นระยะๆ ตลอดเวลาโดยไม่มี HTTP request ใดๆ
เข้ามาเรียก และไม่มี JWT ให้อ่าน tenant — ต่างจากทุก endpoint อื่นในระบบที่
tenant มาจาก JWT claim เสมอ

**ตัวเลือกที่พิจารณา:**
- ตำแหน่งที่รัน: (a) `asyncio.create_task(...)` ใน `backend/main.py`'s
  lifespan (b) process แยกต่างหาก (`alerting/engine.py`)
- แหล่งที่มาของรายชื่อ tenant: (c) connection แบบ superuser
  (`POSTGRES_USER`) bypass RLS แล้ว `SELECT DISTINCT tenant FROM events`
  (d) `SELECT DISTINCT tenant FROM users` ผ่าน `app_user` (ตารางเดียวที่
  ไม่มี RLS อยู่แล้ว — ดู #25)

**สิ่งที่เลือก:** (b) + (d)

**เหตุผล:** (a) จะแชร์ event loop เดียวกับ backend API server — ถ้า
scheduler tick ช้าหรือมีบั๊ก จะไปแย่งเวลา event loop กับการตอบ HTTP request
ซึ่งเป็นงานคนละประเภทกันโดยสิ้นเชิง และมันไม่มีประโยชน์อะไรจาก
`backend/db.py`'s `AsyncConnectionPool` เลย (pool นั้นออกแบบมาสำหรับ
concurrent request หลาย tenant พร้อมกัน แต่ engine ต้องการแค่ connection
เดียวที่ใช้ซ้ำทุก 30 วินาที ตรงกับ pattern ของ `ingest/db.py`'s
`connect_async()` พอดี) (b) แยกเป็น process ของตัวเอง — restart/ดู log
แยกจาก backend ได้ เหมือนที่ `ingest/syslog_server.py` เป็น process แยก
จาก backend อยู่แล้ว ไม่ใช่ของใหม่ในทางสถาปัตยกรรม

สำหรับ tenant: (c) ใช้ superuser bypass RLS ได้ผลลัพธ์เดียวกัน แต่เปิดช่องให้
โค้ด engine ที่มีบั๊กเข้าถึงข้อมูลข้าม tenant ได้แบบไม่มีอะไรกั้นเลย (เพราะ
superuser bypass RLS เสมอ — #6) ขัดกับหลัก defense-in-depth ที่ระบบนี้ยึดถือ
มาตลอด (d) ใช้ `app_user` เดิม (ไม่มี credential ใหม่) กับตาราง `users` ที่ถูก
ออกแบบไว้แล้วว่า "ต้อง query ได้ก่อนรู้ tenant" (เหตุผลเดียวกับที่ login ต้องใช้
มันตั้งแต่ #25) — เป็นการใช้ property เดิมซ้ำ ไม่ใช่ข้อยกเว้นใหม่ หลังจากรู้ชื่อ
tenant แล้ว engine set `app.tenant` ด้วย `set_config()` เหมือน `ingest/db.py`
และ `backend/db.py` ทุกประการ ก่อน query ตารางที่มี RLS ใดๆ ทำให้ RLS ยัง
ป้องกันบั๊กของ engine เองได้เต็มที่ (ไม่ใช่แค่ "เขียน loop ให้ถูก" เท่านั้น)

**ข้อเสียที่ยอมรับ:** tenant ที่มี events แต่ไม่มี user account เลย จะไม่มีทาง
ตั้งค่า alert rule หรือดู alert ได้ (ไม่มีใคร login เข้าไปตั้งค่าได้) — ยอมรับได้
เพราะเป็นข้อจำกัดเดียวกับทั้งระบบอยู่แล้ว: ไม่มี endpoint ไหนใช้ข้อมูลของ tenant
ได้เลยถ้าไม่มี user account อย่างน้อยหนึ่งคน

---

## 41. Webhook: env var เดียว `ALERT_WEBHOOK_URL`, ไม่ตั้งค่า = engine ทำงานปกติ ไม่ error

**บริบท:** โจทย์ระบุแค่ "ส่ง webhook ได้ ตั้งค่าผ่าน env var" — ต้องตัดสินใจว่า
ปลายทาง webhook ผูกกับอะไร และถ้าไม่ได้ตั้งค่าไว้เลยควรเกิดอะไรขึ้น

**ตัวเลือกที่พิจารณา:**
- ปลายทาง: (a) env var เดียวใช้ร่วมกันทุก tenant (b) คอลัมน์ webhook URL แยก
  ต่อ tenant ใน `alert_rules`
- พฤติกรรมเมื่อไม่ได้ตั้งค่า: (c) engine หยุดทำงาน/raise error ตอน startup
  (d) engine ทำงานตามปกติ แค่ข้ามขั้นตอนส่ง webhook

**สิ่งที่เลือก:** (a) + (d)

**เหตุผล:** (a) ตรงกับคำของโจทย์ตรงๆ ("ตั้งค่าผ่าน env var") และไม่ต้องสร้าง
UI/endpoint จัดการ webhook ต่อ tenant ที่ยังไม่มีใครขอ — YAGNI แบบเดียวกับที่
ใช้ตัด role ที่สามใน #24 (d) เพราะ webhook เป็นแค่ "ช่องทางแจ้งเตือนเสริม" ไม่ใช่
ที่เก็บข้อมูล alert จริง — alert ทุกอันถูก insert ลง `alerts` เรียบร้อยแล้วก่อนจะ
พยายามส่ง webhook เสมอ (`GET /alerts` เห็นได้ไม่ว่า webhook จะถูกตั้งค่าไว้หรือไม่)
ดังนั้นการไม่ตั้งค่า `ALERT_WEBHOOK_URL` ไม่ควรทำให้ alerting ทั้งระบบหยุดทำงาน
— `.env.example` เองก็ไม่ได้กำหนดให้ตัวแปรนี้จำเป็น การเช็คว่ามีค่าหรือไม่เกิดขึ้น
ก่อนเรียก `send_webhook()` เสมอ (ไม่ปล่อยให้ไปพังใน `httpx` เอง)

**ข้อเสียที่ยอมรับ:** ไม่มี retry queue สำหรับ webhook ที่ส่งไม่สำเร็จ (`alerts
.webhook_sent_at` จะเป็น `NULL` ทั้งกรณี "ไม่ได้ตั้งค่า" และ "ตั้งค่าแล้วแต่ส่งไม่
สำเร็จ" แยกแยะไม่ได้จากแถวเดียว ต้องดู log ของ engine เพิ่ม) — ยอมรับได้เพราะ
สิ่งที่ assignment ต้องการคือ "เห็น alert ผ่าน UI หรือ webhook" ไม่ใช่การรับประกัน
การส่ง webhook สำเร็จ 100%

---

## 42. JWT ฝั่ง browser เก็บใน `sessionStorage` ไม่ใช่ `localStorage` หรือ in-memory อย่างเดียว

**บริบท:** ต้องตัดสินใจว่า frontend เก็บ JWT (จาก `POST /auth/login`) ไว้ที่ไหน
ใน browser แล้วแนบเป็น `Authorization` header เอง (`frontend/src/api/client.js`)

**ตัวเลือกที่พิจารณา:**
- (a) `localStorage`
- (b) `sessionStorage`
- (c) เก็บใน React state อย่างเดียว ไม่ persist เลย
- (d) httpOnly cookie ที่ browser แนบให้อัตโนมัติ

**สิ่งที่เลือก:** (b)

**เหตุผล:** (d) ถูกตัดตั้งแต่แรกเพราะคำสั่งของ session นี้เอง ("เก็บ JWT แล้วแนบ
Authorization header ทุก request") บอกอยู่แล้วว่า frontend เป็นฝ่ายแนบ header เอง
ซึ่งขัดกับธรรมชาติของ cookie ที่ browser แนบให้อัตโนมัติ — การเปลี่ยนไปใช้ cookie
ต้องแก้ `backend/deps.py`'s `HTTPBearer` scheme ด้วย ซึ่งอยู่นอกขอบเขตของ session
นี้ (ทำแค่ frontend + alerting) ระหว่าง (a)/(b)/(c): (c) บังคับให้ login ใหม่ทุกครั้ง
ที่ reload หน้า เป็นความรำคาญจริงสำหรับ reviewer ที่ต้อง reload ระหว่าง demo 30
นาที (a) กับ (b) ต่างกันแค่ scope ของการ persist — ทั้งคู่เป็น storage ที่
JavaScript อ่านได้เหมือนกันทุกประการ (ถ้ามี XSS ที่ไหนในแอป ก็อ่านได้ทั้งคู่)
เลือก (b) เพราะจำกัดช่วงเวลาที่ token มีอยู่ให้แคบกว่า (หายไปเมื่อปิดแท็บ ไม่ข้าม
แท็บ) โดยไม่เสีย UX เรื่อง reload เลย

**ข้อเสียที่ยอมรับ:** ความปลอดภัยที่แท้จริงจาก XSS ไม่ได้มาจากการเลือก storage
เลย — มันมาจากการไม่มีช่องโหว่ XSS ตั้งแต่แรก (React escape เนื้อหาที่ render โดย
default, ไม่มีจุดไหนในโค้ดใช้ `dangerouslySetInnerHTML`) `sessionStorage` แค่ลด
"หน้าต่างเวลา" ที่ token มีอยู่ ไม่ใช่การป้องกันที่สมบูรณ์

---

## 43. Frontend เพิ่ม `react-router-dom` เป็น dependency ใหม่ ไม่ใช้ Redux/Zustand

**บริบท:** ต้องมี 4 หน้า (Login/Dashboard/Search/Alerts) พร้อม auth guard ที่
redirect กลับ login เมื่อไม่มี token/token หมดอายุ ซึ่ง `CLAUDE.md` กฎข้อ 2
บังคับว่าต้องอธิบายก่อนใช้ library ใหม่ใดๆ

**ตัวเลือกที่พิจารณา:**
- Routing: (a) เขียน routing เอง (เทียบ pathname เอง, จัดการ browser history
  เอง) (b) `react-router-dom`
- State ของ auth (token/claims): (c) Redux/Zustand (d) `React.Context` ธรรมดา

**สิ่งที่เลือก:** (b) + (d)

**เหตุผล:** (a) ต้องเขียนโค้ดจัดการ `history.pushState`, sync กับปุ่ม
back/forward ของ browser, และ nested layout (Dashboard/Search/Alerts ใช้ nav
bar เดียวกันผ่าน `components/Layout.jsx`) เองทั้งหมด — ยาวกว่าและมีจุดพลาดได้
มากกว่าการใช้ router มาตรฐานที่แก้ปัญหาพวกนี้มาแล้ว ในเคสนี้ library มาตรฐาน
อ่านง่ายกว่าโค้ด hand-rolled ตามเจตนารมณ์กฎข้อ 3 ของ `CLAUDE.md` ไม่ใช่ข้อยกเว้น
(b) เป็นเพียง library เดียวที่เพิ่มนอกเหนือ stack ที่ล็อกไว้ สำหรับ state: (c)
เกินความจำเป็นเพราะ state ที่ share ข้ามหน้าจริงๆ มีแค่ก้อนเดียว (JWT +
role/tenant) (d) พอสำหรับขนาดนี้อยู่แล้ว ไม่ต้องเพิ่ม dependency ใหม่อีกตัว

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียที่มีนัยสำคัญสำหรับขนาดแอปนี้ — ถ้าแอปโตขึ้นมาก
ในอนาคต (หลายสิบหน้า, state ที่ซับซ้อนกว่านี้) อาจต้องพิจารณา state library
แยกใหม่

---

## 44. Frontend เรียก `GET /auth/me` หลัง login แทนการ decode JWT เอง

**บริบท:** หลัง login สำเร็จ ต้องรู้ role/tenant ของผู้ใช้เพื่อแสดงผล (เช่น ซ่อน
ปุ่ม save ของฟอร์มแก้ alert rule สำหรับ viewer ใน `pages/AlertsPage.jsx`)

**ตัวเลือกที่พิจารณา:**
- (a) decode JWT payload เองฝั่ง client (base64 decode ส่วนกลางของ token โดย
  ไม่ verify signature เพราะ frontend ไม่มี secret อยู่แล้ว)
- (b) เรียก `GET /auth/me` ที่มีอยู่แล้ว

**สิ่งที่เลือก:** (b)

**เหตุผล:** `/auth/me` มีอยู่แล้วและถูกออกแบบมาเพื่อสิ่งนี้ตรงๆ (คืนค่า claims ที่
verify แล้วจาก payload ที่ `decode_access_token` ตรวจสอบ signature ผ่านมาแล้ว —
ดู `backend/routers/auth.py`) การ decode เองฝั่ง client เป็นโค้ดซ้ำที่ backend
ทำให้แล้ว และเสี่ยงต่อการที่ค่าที่แสดงผลฝั่ง client เพี้ยนไปจากสิ่งที่ server จะ
บังคับจริง (ถ้า claim shape เปลี่ยนในอนาคต ต้องแก้สองที่แทนที่จะแก้ที่เดียว)

**ข้อเสียที่ยอมรับ:** เพิ่ม round-trip เครือข่ายหนึ่งครั้งหลัง login เทียบกับ
decode ในเครื่องที่เร็วกว่า — ยอมรับได้เพราะเกิดแค่ครั้งเดียวตอน login ไม่ใช่ทุก
request

---

## 45. Frontend จัดการ token หมดอายุแบบ reactive เท่านั้น (ไม่มี client-side timer)

**บริบท:** โจทย์ของ session นี้ระบุ "ถ้า token หมดอายุหรือได้ 401 ให้กลับไปหน้า
login"

**ตัวเลือกที่พิจารณา:**
- (a) ตั้ง timer ฝั่ง client ให้ตรงกับ `exp` ของ token แล้ว logout อัตโนมัติเมื่อ
  ถึงเวลา
- (b) ไม่ตั้ง timer ใดๆ — จับแค่ตอนได้ response 401 จริงๆ จาก request ใดๆ
  (`frontend/src/api/client.js`)

**สิ่งที่เลือก:** (b)

**เหตุผล:** token ที่หมดอายุแล้วถูกส่งไปยัง endpoint ใดก็ตาม จะได้ 401 กลับมา
เสมออยู่แล้ว (`decode_access_token` โยน `ExpiredSignatureError`,
`backend/deps.py` แปลงเป็น 401 ทุกกรณีของ `PyJWTError`) ดังนั้น handler เดียว
ที่ดัก 401 ใน `api/client.js` ครอบคลุมทั้งสองกรณีที่โจทย์ระบุ ("หมดอายุ" กับ
"ได้ 401") อยู่แล้วในตัว ไม่ต้องเพิ่ม timer แยกที่ต้องคอย sync กับค่า
`JWT_EXPIRE_MINUTES` ของ backend (ถ้า backend เปลี่ยนค่านี้ frontend ต้องรู้ด้วย
ไม่งั้น timer จะผิดจังหวะ) — YAGNI แบบเดียวกับที่ backend เองไม่ทำ token
revocation ใน #32

**ข้อเสียที่ยอมรับ:** ถ้าผู้ใช้ไม่ trigger request ใดๆ เลยหลัง token หมดอายุ
(เปิดหน้าทิ้งไว้เฉยๆ ไม่ interact) จะไม่ถูกเด้งออกทันทีที่หมดอายุเป๊ะๆ — จะถูก
เด้งออกก็ต่อเมื่อมี request ครั้งถัดไป ยอมรับได้เพราะไม่ใช่ security boundary จริง
(การเข้าถึงข้อมูลถูกบังคับที่ backend อยู่แล้วไม่ว่า UI จะรู้ตัวช้าแค่ไหน)

---

## 46. CORS: allowlist origin เดียวจาก env var, ไม่ใช้ credentials mode

**บริบท:** browser บล็อก cross-origin fetch จาก frontend (Vite dev server,
คนละ origin กับ backend) โดย default ต้องเปิด CORS ที่ backend
(`backend/main.py`)

**ตัวเลือกที่พิจารณา:**
- (a) `allow_credentials=True` (จำเป็นถ้าใช้ cookie-based auth)
- (b) `allow_credentials=False` พร้อม allowlist origin เดียวจาก
  `FRONTEND_ORIGIN`

**สิ่งที่เลือก:** (b)

**เหตุผล:** ระบบนี้ไม่เคยใช้ cookie เลย (ดู #42 — JWT อยู่ใน `sessionStorage`,
แนบเป็น `Authorization` header เอง) จึงไม่มีเหตุผลต้องเปิด credentialed-CORS
ซึ่งมีข้อจำกัดเพิ่ม (เช่น ห้ามใช้ `allow_origins=["*"]` ร่วมกับ credentials) —
allowlist ธรรมดาพร้อม origin เดียวที่ config ผ่าน env var ง่ายกว่าและตรงกับสิ่ง
ที่ระบบต้องการจริง

**ข้อเสียที่ยอมรับ:** ไม่มีข้อเสียที่มีนัยสำคัญ — เป็นการเลือก mode ที่ตรงกับ
สถาปัตยกรรมที่มีอยู่แล้วเป๊ะ

---

## 47. Dashboard: Top IP/User/Event Type แสดงเป็นตาราง ไม่ใช่ bar chart

**บริบท:** โจทย์ (§2.2) ต้องการ "Top IP/User/Event Type" บน dashboard โดยไม่ได้
ระบุรูปแบบการแสดงผล

**ตัวเลือกที่พิจารณา:**
- (a) bar chart ด้วย Recharts (เหมือน timeline)
- (b) ตาราง HTML ธรรมดา (อันดับ/ค่า/จำนวน — `components/TopNTable.jsx`)

**สิ่งที่เลือก:** (b)

**เหตุผล:** Top-N แต่ละอันมีแค่ ~10 แถว การอ่าน "ค่าอะไร → จำนวนเท่าไหร่" จาก
ตารางตรงไปตรงมากว่าการกะความยาวแท่ง โดยเฉพาะเมื่อค่า (IP address, username) เป็น
string ยาวๆ ที่ใส่บน bar chart จะอ่านยาก — สงวน Recharts ไว้กับ timeline ที่
chart ให้คุณค่าจริง (เห็น trend ตามเวลา ซึ่งตารางไม่ทำได้ดีเท่า)

**ข้อเสียที่ยอมรับ:** ไม่มีนัยสำคัญ — ตารางกับ bar chart ให้ข้อมูลเดียวกันครบถ้วน
แค่รูปแบบการแสดงผลต่างกัน

---

## 48. ยังไม่มี frontend Docker service หรือ Caddy TLS ใน session นี้

**บริบท:** `docker-compose.yml` มี comment เดิมตั้งแต่ session ก่อนว่า
"Frontend/caddy are added in later sessions"

**ตัวเลือกที่พิจารณา:**
- (a) เพิ่ม frontend service (nginx serve static build) + Caddy TLS ใน session
  นี้ด้วย
- (b) ปล่อยให้ demo ผ่าน `npm run dev` ตรงๆ กับ backend ที่ dockerize ไว้แล้ว

**สิ่งที่เลือก:** (b)

**เหตุผล:** ขอบเขตของ session นี้ตามคำสั่งคือ "frontend และ alerting" ไม่ใช่
deployment/packaging — `npm run dev` ชี้ไปที่ backend ที่รันผ่าน `make up` ได้
อยู่แล้ว เพียงพอสำหรับ demo และทดสอบ ไม่ต้องเพิ่ม Docker service ใหม่ที่ไม่มี
อะไรให้ทดสอบเพิ่มในเซสชันนี้ (TLS ยังไม่ implement เลยทั้งระบบ ไม่ใช่แค่
frontend)

**ข้อเสียที่ยอมรับ:** ผู้ตรวจต้องรัน `npm install && npm run dev` เองแทนที่จะ
ได้ frontend มาพร้อมกับ `make up` ตัวเดียว — ต้อง implement ในเซสชัน
deployment/SaaS ที่ตามมาถึงจะครบทั้ง 2 โหมด (appliance/SaaS) ตามที่โจทย์ต้องการ
จริงๆ

---

## 49. `npm audit` มีช่องโหว่ 4 รายการที่ตั้งใจไม่แก้ในเซสชันนี้ + ไม่ upgrade `recharts` ไป major version 3

**บริบท:** `npm install` ของ `frontend/` รายงาน 4 ช่องโหว่ (3 moderate, 1 high)
และ deprecation warning ของ `recharts@2.x` แนะนำให้ bump เป็น v3 — ต้องตัดสินใจ
ว่าจะแก้ตามคำแนะนำอัตโนมัติหรือไม่ ก่อนจะยืนยันเวอร์ชันสุดท้ายใน
`frontend/package.json`

**รายละเอียดที่พบจริงจาก `npm audit`:**
1. `esbuild <=0.24.2` (ผ่าน `vite`) — "enables any website to send any
   request to the dev server and read the response" — severity moderate
2. `react-router 6.0.0-7.17.0` (ผ่าน `react-router-dom`) — open redirect ผ่าน
   backslash ใน `<Link>`/`useNavigate`, และช่องโหว่ arbitrary constructor
   injection ใน SSR hydration's `deserializeErrors()`

**ตัวเลือกที่พิจารณา:**
- (a) `npm audit fix --force` (จะ upgrade `vite` เป็น major version 8 และ
  `react-router-dom` เป็น major version 7 — ทั้งคู่เป็น breaking change)
- (b) ปล่อยไว้ตามเวอร์ชันปัจจุบัน พร้อมบันทึกเหตุผลว่าทำไมความเสี่ยงจริงของแอปนี้
  ต่ำ

**สิ่งที่เลือก:** (b)

**เหตุผล:**
- ช่องโหว่ `esbuild` กระทบเฉพาะตอนรัน **dev server** เท่านั้น (ไม่ใช่ production
  build ที่ deploy จริง) และ appliance/SaaS ตามโจทย์ไม่ได้เปิด dev server ให้
  คนนอกเข้าถึง — ผลกระทบจึงจำกัดอยู่แค่เครื่อง dev ของผู้พัฒนาเอง
- ช่องโหว่ SSR ของ `react-router` ไม่เกี่ยวกับแอปนี้เลยเพราะเป็น client-side
  rendering (CSR) ล้วนๆ ไม่มี SSR ใดๆ
- ช่องโหว่ open-redirect ของ `react-router` ต้องการ input ที่ผู้โจมตีควบคุมได้
  ไปยัง `<Link>`/`useNavigate` โดยตรง — ทุกจุดในแอปนี้ที่เรียก `Navigate`/
  `useNavigate` (`App.jsx`, `AuthContext.jsx`, `LoginPage.jsx`,
  `ProtectedRoute.jsx`) ใช้ path คงที่ที่เขียนไว้ในโค้ดเอง (`/login`,
  `/dashboard`) ไม่เคยรับ path จาก user input หรือ query param เลย จึงไม่มีช่อง
  ให้ใช้ประโยชน์จากช่องโหว่นี้ได้จริงในสถาปัตยกรรมนี้
- การ `--force` upgrade ทั้ง `vite` (v5→v8) และ `react-router-dom` (v6→v7) เป็น
  breaking change สองตัวพร้อมกันโดยไม่มีเวลาไล่ debug/verify migration ใน
  เซสชันนี้ มีความเสี่ยงทำให้ของที่ทำงานอยู่แล้วพังมากกว่าประโยชน์ที่ได้จาก
  ช่องโหว่ที่ไม่ apply กับการใช้งานจริงของแอปนี้

สำหรับ `recharts`: ระหว่างแก้ปัญหานี้ เกือบ bump `recharts` จาก `^2.12.7` เป็น
`^3.2.1` ตาม deprecation notice ของ `npm install` โดยยังไม่ได้ตรวจสอบว่า API ที่
`TimelineChart.jsx` ใช้ (`AreaChart`, `ResponsiveContainer`, `CartesianGrid`,
`Tooltip`) เข้ากันได้กับ v3 หรือไม่ — ถูกทักท้วงและแก้กลับก่อน commit จริง
ยืนยันแล้วว่า `npm install` ติดตั้ง `recharts@2.15.4` จริง (ตรงกับ spec
`^2.12.7` เดิม ไม่ใช่ผล resolve เป็น 3.x เอง) และ `npm run build` ผ่านสำเร็จกับ
เวอร์ชันนี้ — คงไว้ที่ major version 2 ตามที่โค้ดเขียนไว้จริง ไม่ใช่ตาม
คำแนะนำในข้อความ install log เฉยๆ

**ข้อเสียที่ยอมรับ:** หนี้ทางเทคนิค (technical debt) ที่ต้องกลับมาพิจารณาใหม่ถ้า:
(1) เซสชันในอนาคตเปิด dev server ให้เข้าถึงจากภายนอกจริงๆ (ไม่ใช่แค่ localhost
ของผู้พัฒนา) ซึ่งจะทำให้ช่องโหว่ `esbuild` มีผลจริง (2) มีจุดในแอปที่เริ่มรับ
redirect target จาก user input ในอนาคต ซึ่งจะทำให้ช่องโหว่ `react-router`
open-redirect มีผลจริง (3) ต้องการ feature ใหม่ที่มีแค่ใน `recharts` v3 หรือ
`react-router` v7 — ตอนนั้นต้องจัดเวลา verify migration ให้เพียงพอก่อน upgrade
ไม่ใช่ bump เฉยๆ ตามคำแนะนำใน install log แบบที่เกือบทำผิดพลาดไปในเซสชันนี้

---

## 50. Routing แบบ single-origin path-based (`/` → frontend, `/api/*` → backend) แทนแยก subdomain

**บริบท:** ต้องเพิ่ม Caddy เป็น reverse proxy หน้าสุดสำหรับ frontend (static
build) กับ backend (FastAPI) และต้องตัดสินใจว่า frontend/backend จะอยู่ origin
เดียวกันหรือคนละ origin (subdomain แยก)

**ตัวเลือกที่พิจารณา:**
- (a) แยก subdomain: `app.example.com` (frontend), `api.example.com`
  (backend)
- (b) origin เดียวกัน แบ่งด้วย path prefix: `/` → frontend, `/api/*` →
  backend (strip prefix ก่อนส่งต่อ)

**สิ่งที่เลือก:** (b)

**เหตุผล:** (a) ต้องมี DNS record 2 รายการ, ต้องขอ cert แยก 2 ใบ (หรือ wildcard
cert ที่ต้องทำ DNS-01 challenge ผ่าน DNS provider API — เพิ่ม credential ใหม่ที่
ต้องดูแล ขัดกับกฎ "ห้ามเขียนค่า secret จริงลงไฟล์ใดๆ" ของ `CLAUDE.md` โดยไม่
จำเป็น) และที่สำคัญที่สุดคือทำให้ frontend กับ backend กลับมาเป็นคนละ origin
— ต้องพึ่ง CORS ข้ามจริงอีกครั้ง ในขณะที่ `backend/config.py`'s
`FRONTEND_ORIGIN` ปัจจุบันรองรับแค่ origin เดียว (string ไม่ใช่ list) จะต้องแก้
โค้ด backend ให้รองรับ multi-origin CORS ด้วย ซึ่งอยู่นอกขอบเขตของ session นี้
("ทำเฉพาะ packaging และ TLS") ส่วน (b) ต้องการแค่ DNS record เดียว, cert ใบ
เดียว (HTTP-01 challenge แบบง่ายที่สุดของ Let's Encrypt ไม่ต้องมี DNS API),
ไม่ต้องแก้โค้ด backend เลย และทำให้ frontend image เดียวใช้ได้ทั้ง appliance/
SaaS โดยไม่ต้อง bake absolute domain ไว้ตอน build (ดูข้อ 51)

**ข้อเสียที่ยอมรับ:** ต้องมี Caddy directive `handle_path /api/*` (strip prefix
`/api` ก่อนส่งต่อให้ backend เพราะ router จริงของ backend ไม่มี prefix `/api`
เลย — ยืนยันจากโค้ดจริง: `auth.py` ใช้ `prefix="/auth"`, `ingest.py` เป็น
`POST /ingest` ตรงๆ ตามที่โจทย์ PDF ระบุไว้, `stats.py` ใช้ `prefix="/stats"`)
เป็นความซับซ้อนเล็กน้อยที่ต้องเข้าใจเพิ่ม แต่เป็น directive มาตรฐานของ Caddy
ไม่ใช่ library ใหม่

---

## 51. `VITE_API_BASE_URL=/api` (relative, bake ตอน build) แทน runtime-config injection — ให้ image เดียวใช้ได้ทั้ง 2 โหมด

**บริบท:** `frontend/src/api/client.js` อ่าน `import.meta.env.VITE_API_BASE_URL`
ซึ่ง Vite แทนที่เป็น string literal ตอน `vite build` (build-time ไม่ใช่
runtime) — ไม่มี runtime-config mechanism ใดๆ อยู่แล้วในโค้ดเดิม (ไม่มี
`window.__ENV__`, ไม่มี fetch `config.json` ตอน container start) ต้อง
ตัดสินใจว่าจะทำให้ image เดียวใช้ได้ทั้ง appliance และ SaaS ได้อย่างไร ในเมื่อ
ค่านี้ถูกล็อกไว้ตั้งแต่ตอน build image

**ตัวเลือกที่พิจารณา:**
- (a) เพิ่ม runtime-config pattern ใหม่ (entrypoint script generate
  `config.js` จาก env ตอน container start, `index.html` โหลดก่อน bundle,
  แก้โค้ด frontend ให้อ่าน `window.__ENV__` แทน `import.meta.env`)
- (b) build image แยกกัน 2 ชุดต่อโหมด (คนละ `VITE_API_BASE_URL` ตอน build)
- (c) bake ค่า `VITE_API_BASE_URL=/api` (relative path) เป็นค่า default
  เดียวตอน build โดยอาศัยว่า frontend/backend อยู่หลัง Caddy origin เดียวกัน
  เสมอทั้ง 2 โหมด (ข้อ 50)

**สิ่งที่เลือก:** (c)

**เหตุผล:** (a) แก้ปัญหาได้จริงแต่เป็น "pattern ที่ยังไม่ได้อธิบายมาก่อน" ตามกฎ
ข้อ 2 ของ `CLAUDE.md` และเพิ่มโค้ดใหม่ (entrypoint script + แก้ frontend
source) โดยไม่จำเป็น (b) ขัดกับที่โจทย์ต้องการ "image เดียวใช้ได้ทั้งสองโหมด"
ตรงๆ ส่วน (c) relative path ใช้ได้เหมือนกันไม่ว่า origin จริงจะเป็น
`https://localhost` (appliance) หรือ `https://yourdomain.com` (SaaS) เพราะไม่
ต้อง encode hostname ไว้เลย — เป็นทางเดียวที่ทำให้ "image เดียวใช้ได้ทั้งสอง
โหมด" เป็นจริงได้โดยไม่ต้องเพิ่ม pattern ใหม่

**ข้อเสียที่ยอมรับ:** บังคับให้การตัดสินใจเรื่อง routing (ข้อ 50) ต้องเป็นแบบ
single-origin path-based เท่านั้น เลือก subdomain แยกไม่ได้ถ้าไม่อยากเสีย
property นี้ไป — และมีค่า `VITE_API_BASE_URL` อยู่ 2 จุดที่ต้อง**ต่างค่ากันโดย
เจตนา**ตลอด (`docker-compose.yml`'s build arg = `/api`,
`frontend/.env.example` สำหรับ `npm run dev` = `http://localhost:8000`
เพราะ `vite.config.js` ไม่มี `server.proxy`) ซึ่งเป็นจุดที่คนในอนาคตอาจ
copy ค่าผิดที่แล้วงงว่าทำไม dev server ได้ 404 — บรรเทาด้วย comment อธิบายไว้
ในทั้งสองไฟล์ `.env.example`

---

## 52. ใช้ `caddy:2-alpine` เป็น static file server ของ frontend image แทน `nginx`

**บริบท:** `frontend/Dockerfile` stage สุดท้ายต้อง serve static build
(`dist/`) ด้วย image เล็ก ต้องเลือกว่าจะใช้อะไรเป็น static file server

**ตัวเลือกที่พิจารณา:**
- (a) `nginx:alpine` — ตัวเลือกมาตรฐานที่นิยมที่สุดสำหรับ serve SPA static
  build (~23MB)
- (b) `caddy:2-alpine` — ใช้ Caddy ตัวเดียวกับที่เป็น proxy/TLS หลักของ stack
  อยู่แล้ว (~40MB)

**สิ่งที่เลือก:** (b) — ยืนยันกับผู้ใช้แล้วก่อนเขียนโค้ด (ผู้ใช้เลือก (b) จาก
คำถามที่ถามตรงๆ ระหว่าง planning)

**เหตุผล:** `CLAUDE.md` ล็อก "Proxy/TLS: Caddy" ไว้เป็น stack เดียวที่อธิบาย/
justify ไว้แล้ว การเพิ่ม `nginx` เป็น static server จะเป็นการนำ tool ใหม่ที่ยัง
ไม่ได้อธิบายเข้ามาตามกฎข้อ 2 ของ `CLAUDE.md` ("ห้ามใช้ library หรือ pattern ที่
ยังไม่ได้อธิบายก่อนใช้") ในขณะที่ Caddy's `file_server` directive ทำงานเดียวกัน
ได้ด้วยบรรทัดเดียว ไม่ต้องเขียน config ใหม่ (`nginx.conf` พร้อม `try_files` ของ
ตัวเอง) และลดจำนวนเทคโนโลยีที่ต้องอธิบายในวิดีโอเดโมเหลือแค่ตัวเดียว (Caddy)
แทนที่จะมี 2 ตัว (Caddy + nginx)

**ข้อเสียที่ยอมรับ:** มี Caddy 2 ชั้นซ้อนกัน (ชั้นนอก = proxy/TLS, ชั้นใน =
static file server) ซึ่งอาจดูแปลกกว่ารูปแบบทั่วไป (nginx serve static +
Caddy/nginx อื่น proxy) และ image ใหญ่กว่า `nginx:alpine` เล็กน้อย (~40MB vs
~23MB) — ยอมรับได้เพราะไม่ใช่ต้นทุนที่มีนัยสำคัญสำหรับ demo/assignment นี้ และ
แลกกับการไม่ต้องแนะนำ tool ใหม่ที่ต้องอธิบายเพิ่ม

---

## 53. แยก `Caddyfile`/`Caddyfile.saas` เป็น 2 ไฟล์ สลับด้วย compose override แทน env-var templating ไฟล์เดียว

**บริบท:** ต้องรองรับ 2 โหมดของ TLS: self-signed (appliance/dev, ไม่มี domain
จริง) กับ Let's Encrypt อัตโนมัติ (SaaS, มี domain จริง) — Caddy รองรับทั้งคู่
ในตัวแต่ใช้ directive ต่างกันตรงๆ

**ตัวเลือกที่พิจารณา:**
- (a) Caddyfile ไฟล์เดียว ใช้ env var placeholder (`{$VAR}`) สลับพฤติกรรม
  TLS ผ่านค่า env ที่ต่างกัน
- (b) แยกเป็น 2 ไฟล์ (`Caddyfile` = appliance default, `Caddyfile.saas` =
  SaaS) สลับกันด้วย `docker-compose.saas.yml` mount คนละไฟล์เข้า
  `/etc/caddy/Caddyfile`

**สิ่งที่เลือก:** (b)

**เหตุผล:** directive ของทั้ง 2 โหมดต่างกันเป็น statement คนละแบบจริงๆ ไม่ใช่
แค่ค่าต่างกันของ statement เดียวกัน (appliance ต้องมี `tls internal`,
SaaS ต้องไม่มี `tls internal` เลยแต่มี global option `email` แทน) — การพยายาม
ทำ `{$VAR}` templating ให้ครอบคลุมทั้ง "มี directive นี้" กับ "ไม่มี directive
นี้เลย" ในไฟล์เดียวจะซับซ้อนและอ่านยาก (ต้องพึ่งพฤติกรรมของ Caddy ตอน env
ว่างเปล่า ซึ่งไม่ตรงไปตรงมา) ขัดกับกฎข้อ 3 ของ `CLAUDE.md` ที่ให้เลือกโค้ดอ่าน
ง่ายเสมอแม้จะยาวกว่า ส่วน (b) แต่ละไฟล์สั้น อ่านจบในตาก็เข้าใจ TLS mode ของมัน
ทันที และตรงกับ pattern ที่ `CLAUDE.md` ล็อกไว้อยู่แล้ว ("ใช้ compose override
แทนการแยกไฟล์เต็มสองชุด" — ในที่นี้ override แค่ 1 field คือ volume mount ของ
Caddyfile ไม่ใช่ copy ทั้ง `docker-compose.yml`)

**ข้อเสียที่ยอมรับ:** มี 2 ไฟล์ที่ต้อง sync ส่วน routing logic ที่เหมือนกัน
(`handle_path /api/*` → backend, `handle` → frontend) ด้วยมือ ถ้าแก้ routing
ในอนาคตต้องจำไว้ว่าต้องแก้ทั้งคู่ — ยอมรับได้เพราะไฟล์เล็กมาก (ไม่กี่บรรทัด)
และความเสี่ยงลืมแก้ไฟล์ใดไฟล์หนึ่งต่ำกว่าความเสี่ยงจาก env-var templating ที่
อ่าน/debug ยากกว่ามาก

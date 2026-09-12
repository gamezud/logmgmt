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

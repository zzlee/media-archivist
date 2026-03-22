# MediaArchivist 開發規格書 (v1.0)

## 技術規格
- **Language**: Python 3.12+
- **Manager**: uv
- **Database**: SQLite (WAL mode for concurrency)
- **CLI**: Typer
- **Web**: FastAPI

## 資料庫結構 (Schema)
| 欄位 | 型別 | 說明 |
| :--- | :--- | :--- |
| abs_path | TEXT | 唯一路徑 (PK) |
| file_size | INTEGER | 檔案大小 |
| sha256_hash | TEXT | 特徵值 (Index) |
| status | TEXT | pending/hashing/completed |

## 開發里程碑 (v1.0)
1. [x] CLI 掃描器與 SQLite 整合
2. [x] 背景 Hash 計算代理 (Agent)
3. [x] 重複檔案清單 API
4. [x] Web 手動篩選 Dashboard

## 開發里程碑 (v1.1 - 進階清理與多源支援)
1. [x] 支援同時掃描多個目錄
2. [x] CLI 自動去重清理指令 (Cleanup)
3. [x] 優先規則：保留最短路徑檔案
4. [x] 整合 Git 版本控制

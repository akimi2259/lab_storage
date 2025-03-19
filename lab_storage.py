import streamlit as st
# import cv2
from pyzbar import pyzbar
import requests
import json
from PIL import Image
import os
from typing import Optional, List, Dict, Any
import datetime
import time
import pandas as pd

# 環境変数にNotion APIトークンを設定
os.environ['API_KEY'] = st.secrets["NOTION_API_KEY"]
os.environ['NOTION_DATABASE_ID'] = st.secrets["NOTION_DATABASE_ID"]
os.environ['MASTER_DATABASE_ID'] = st.secrets["MASTER_DATABASE_ID"]
os.environ['LOG_DATABASE_ID'] = st.secrets["LOG_DATABASE_ID"]

# 環境変数からNotion APIトークンを取得
notion_token: str = os.environ['API_KEY']
zaiko_database_id: str = os.environ['NOTION_DATABASE_ID']
master_database_id: str = os.environ['MASTER_DATABASE_ID']
log_database_id: str = os.environ['LOG_DATABASE_ID']

# Notion APIクライアントの設定
headers: Dict[str, str] = {
    "Authorization": f"Bearer {notion_token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# NotionデータベースのURL
master_url: str = f"https://api.notion.com/v1/databases/{master_database_id}/query"
log_url: str = f"https://api.notion.com/v1/databases/{log_database_id}/query"
zaiko_url: str = f"https://api.notion.com/v1/databases/{zaiko_database_id}/query"

# def read_barcode(image: cv2.typing.MatLike) -> Optional[str]:
#     """
#     画像からバーコードを読み取る関数。

#     Args:
#         image: バーコードを含む画像。

#     Returns:
#         読み取られたバーコードのデータ（文字列）、またはバーコードが読み取れなかった場合はNone。
#     """
#     barcodes = pyzbar.decode(image)
#     for barcode in barcodes:
#         barcode_data = barcode.data.decode("utf-8")
#         return barcode_data
#     return None

def confirm_product(
        product_id: str, 
        product_image: Image.Image, 
        product_name: str, 
        company: str
        ) -> bool:
    """
    製品情報を確認するためのポップアップを表示する関数。

    Args:
        product_id: 製品ID。
        product_image: 製品画像。
        product_name: 製品名。
        company: 会社名。

    Returns:
        確認された場合はTrue、拒否された場合はFalse。
    """
    st.image(
        product_image,
        #caption=f"Product number: {product_id} \n Product name: {product_name} \n Company: {company}",
        width=200,
    )

    st.write(f"この製品を確認してください。  \n Product number: {product_id}  \n Product name: {product_name}  \n Company: {company}")

    if 'product_confirmed' not in st.session_state:
        st.session_state.product_confirmed = False

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirm"):
            st.session_state.product_confirmed = True
            return True
    with col2:
        if st.button("Refuse"):
            st.session_state.product_confirmed = False
            return False

    return st.session_state.product_confirmed

def update_inventory(
    product_id: str, 
    action: str, 
    quantity: int = 1, 
    url: str = zaiko_url
) -> bool:
    """
    Notionデータベースの在庫情報を更新する関数。

    Args:
        product_id: 製品ID。
        action: 実行されたアクション（"入庫", "開封", "廃棄"）。
        quantity: 更新する数量。
        url: 在庫データベースのURL。

    Returns:
        更新が成功した場合はTrue、失敗した場合はFalse。
    """
    query: Dict[str, Any] = {
        "filter": {
            "property": "product number",
            "number": {
                "equals": product_id
            }
        }
    }
    response = requests.post(url, headers=headers, data=json.dumps(query), verify=True)
    data = response.json()
    results = data.get("results", [])
    if results:
        page_id = results[0]["id"]
        inventory = int(results[0]["properties"]["stock quantity"]["number"])
        if action == "入庫":
            inventory += quantity
        elif action == "開封":
            inventory -= quantity
        elif action == "廃棄":
            inventory -= 0  # 箱単位で管理するなら、この項目による増減は不要になるはず。
        update_query: Dict[str, Any] = {
            "properties": {
                "stock quantity": {
                    "number": inventory
                }
            }
        }
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        requests.patch(update_url, headers=headers, data=json.dumps(update_query), verify=True)
        return True
    return False

def log_action(
    zaiko_database_id: str,
    product_number: int,
    product_name: str,
    status: str,
    quantity: int,
    user_name: str,
    note: str = "",
    storages: List[str] = ["572", "573", "575", "576", "587", "588"],
) -> bool:
    """
    Notionデータベースにログ情報を追加する関数。

    Args:
        zaiko_database_id: ログを記録するデータベースID。
        product_number: 製品番号。
        product_name: 製品名。
        status: 実行されたアクション（"入庫", "開封", "廃棄"）。
        quantity: 数量。
        user_name: ユーザー名。
        note: 備考。
        storages: 保管場所のリスト。

    Returns:
        ログの追加が成功した場合はTrue、失敗した場合はFalse。
    """
    dt_now = datetime.datetime.now()

    log_entry: Dict[str, Any] = {
        "parent": {"database_id": zaiko_database_id},
        "properties": {
            "date": {"date": {"start": dt_now.strftime("%Y-%m-%d")}},
            "product name": {"title": [{"text": {"content": product_name}}]},
            "product number": {"number": product_number},
            "quantity": {"number": quantity},
            "status": {"select": {"name": status}},
            "user_name": {"rich_text": [{"text": {"content": user_name}}]},
            "storage": {"multi_select": [{"name": storage} for storage in storages]},
            "note": {"rich_text": [{"text": {"content": note}}]},
        }
    }

    response = requests.post(
        "https://api.notion.com/v1/pages", 
        headers=headers, 
        data=json.dumps(log_entry), 
        verify=True,
    )
    if response.status_code == 200:
        return True
    else:
        print(response.text)
        return False
    
def get_top_n_rows(database_id: str, n: int, headers: Dict[str, str]) -> pd.DataFrame:
    """
    Retrieves the top n rows from a Notion database and returns them as a pandas DataFrame.

    Args:
        database_id: The ID of the Notion database.
        n: The number of top rows to retrieve.
        headers: The headers for the Notion API request.

    Returns:
        A pandas DataFrame containing the top n rows from the Notion database.  Returns an empty DataFrame if there's an error or no results.
    """
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    response = requests.post(url, headers=headers, data=json.dumps({"page_size": n}), verify=True)

    try:
        data = response.json()
        if response.status_code == 200:
            results = data["results"][:n]  # Slice the results to get only the top n
            #Handle empty results
            if not results:
                return pd.DataFrame()
            #Convert to DataFrame.  This handles nested dictionaries better than pd.read_json
            return pd.DataFrame.from_records(results)
        else:
            print(f"Error fetching data: {response.status_code} - {response.text}")
            return pd.DataFrame()  # Return empty DataFrame on error
    except json.JSONDecodeError:
        print(f"Error decoding JSON response: {response.text}")
        return pd.DataFrame()
    except KeyError:
        print(f"Unexpected response format: {response.text}")
        return pd.DataFrame()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return pd.DataFrame()

def process_notion_data(database_id: str, n: int, headers: Dict[str, str]) -> pd.DataFrame:
    """Processes a list of Notion API responses into a pandas DataFrame.

    Args:
        notion_data: A list of dictionaries, where each dictionary represents a row from the Notion API response.

    Returns:
        A pandas DataFrame with the processed data. Returns an empty DataFrame if input is invalid or empty.
    """
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    response = requests.post(url, headers=headers, data=json.dumps({"page_size": n}), verify=True)
    notion_data = response.json().get("results")
    if not notion_data:
        return pd.DataFrame()
    
    processed_data = []
    for row in notion_data:
        properties = row["properties"]
        processed_row = {}
        for key, value in properties.items():
            # Handle different property types
            if value.get("type") == "date":
                processed_row[key] = value["date"].get("start")
            elif value.get("type") == "title":
                processed_row[key] = value["title"][0]["text"]["content"] if value["title"] else ""
            elif value.get("type") == "number":
                processed_row[key] = value["number"]
            elif value.get("type") == "select":
                processed_row[key] = value["select"]["name"]
            elif value.get("type") == "rich_text":
                processed_row[key] = value["rich_text"][0]["text"]["content"] if value["rich_text"] else ""
            elif value.get("type") == "multi_select":
                processed_row[key] = ", ".join([item["name"] for item in value["multi_select"]])
            else:
                processed_row[key] = str(value) # Handle other types as strings

        processed_data.append(processed_row)

    return pd.DataFrame.from_records(processed_data)

# Example usage: Get the top 5 rows from your database
top_5_rows = process_notion_data(database_id=log_database_id, n=5, headers=headers)
if top_5_rows is not None:
    st.dataframe(
        top_5_rows[["date", "product number", "product name", "user_name", "storage", "status", "quantity", "note"]],
        hide_index=True,
        #use_container_width=True,
    )
else:
    st.write("Failed to retrieve data from Notion.")



# Main App
st.title("Inventory Management App")

# セッション状態の初期化
if 'step' not in st.session_state:
    st.session_state.step = 'scan'  # 'scan', 'confirm', 'update', 'add_master'

# カメラでバーコードを読み取る
if st.session_state.step == 'scan':
    # if st.button("Scan Barcode"):
    #     cap = cv2.VideoCapture(0)
    #     while True:
    #         ret, frame = cap.read()
    #         if not ret:
    #             break
    #         barcode_data = read_barcode(frame)
    #         if barcode_data:
    #             break
    #         cv2.imshow('Scan Barcode', frame)
    #         if cv2.waitKey(1) & 0xFF == ord('q'):
    #             break
    #     cap.release()
    #     cv2.destroyAllWindows()

    #     if barcode_data:
    #         st.write(f"Scanned Barcode: {barcode_data}")
    #         product_id = barcode_data
    #         st.session_state.product_id = product_id
    #         st.session_state.step = 'confirm'
    #         st.rerun()
    #     else:
    #         product_id = st.text_input("Enter Product ID")
    #         if product_id:
    #             st.session_state.product_id = product_id
    #             st.session_state.step = 'confirm'
    #             st.rerun()
    # else:
        product_id = st.number_input("製品番号(product number)を入力してください", 
                                     min_value=0, 
                                     step=1, 
                                     #format="%6d",
                                     )
        if st.button("製品番号を確認"):
            st.session_state.product_id = product_id
            st.session_state.step = 'confirm'
            st.rerun()

elif st.session_state.step == 'confirm':
    product_id = st.session_state.product_id
    # 製品情報を取得
    query: Dict[str, Any] = {
        "filter": {
            "property": "product number",
            "number": {
                "equals": product_id
            }
        }
    }
    response = requests.post(master_url, headers=headers, data=json.dumps(query), verify=True)
    data = response.json()
    results = data.get("results", [])
    if results:
        st.session_state.storage = results[0]["properties"]["where"]["multi_select"][0]["name"]
        product_image = results[0]["properties"]["image"]["files"][0]["file"]["url"]
        image = Image.open(requests.get(product_image, stream=True).raw)
        product_name = results[0]["properties"]["product name"]["rich_text"][0]["text"]["content"]
        company = results[0]["properties"]["company"]["rich_text"][0]["text"]["content"]

        # 確認プロセス
        confirmed = confirm_product(product_id, image, product_name, company)

        if confirmed:
            st.session_state.product_name = product_name
            st.session_state.step = 'update'
            st.session_state.product_confirmed = False
            st.rerun()

        elif st.button("戻る"):
            st.session_state.step = 'scan'
            st.session_state.product_confirmed = False
            st.rerun()
    else:
        st.error("製品が見つかりません")
        if st.button("戻る"):
            st.session_state.step = 'scan'
            st.rerun()
        elif st.button("マスター登録"):
            st.session_state.step = 'add_master'
            st.rerun()

elif st.session_state.step == 'update':
    # 在庫更新フォーム
    st.write(f"製品番号 {st.session_state.product_id} ({st.session_state.product_name}) の在庫状況を設定します。")

    action = st.selectbox("Select Action", ["入庫", "開封", "廃棄"])
    quantity = st.number_input("個数を入力してください", min_value=1, value=1)
    user_name = st.text_input("ユーザー名を入力してください", "bneiea")
    storages = st.multiselect("保管場所を選択してください", ["572", "573", "575", "576", "587", "588"], [st.session_state.storage])
    note = st.text_area("備考を入力してください", "")

    if st.button("Update Inventory"):
        product_id = st.session_state.product_id
        product_name = st.session_state.product_name

        if update_inventory(product_id, action, quantity):
            st.success(f"Inventory updated for {product_id}")
            log_action(
                zaiko_database_id=log_database_id,
                product_number=product_id,
                product_name=product_name,
                status=action,
                quantity=quantity,
                user_name=user_name,
                note=note,
                storages=storages,
            )
            # 更新完了後、最初のステップに戻る
            st.session_state.step = 'scan'
            if st.button("restart step"):
                st.rerun()
        else:
            st.error(f"Failed to update inventory for {product_id}")

    if st.button("キャンセル"):
        st.session_state.step = 'scan'
        st.rerun()

elif st.session_state.step == 'add_master':
    st.write("マスター登録フォーム")
    product_id = st.session_state.product_id
    st.write(f"製品番号: {product_id}")
    product_name = st.text_input("製品名を入力してください")
    company = st.text_input("会社名を入力してください")
    product_info = st.text_input("製品情報を入力してください")
    storages = st.multiselect("保管場所を選択してください", ["572", "573", "575", "576", "587", "588"], ["573"])
    note = st.text_input("備考を入力してください")
    image_url = st.text_input("可能なら画像URLを入力してください")
    #st.session_state.image = False
    if image_url:
        image = Image.open(requests.get(image_url, stream=True).raw)
        st.image(image, caption="Image URL", use_container_width=True)
        #st.session_state.image = True
    

    #image_url = st.camera_input("商品画像をとってください。")
    #image_url = st.text_input("画像URLを入力してください", "")

    if st.button("マスター登録"):
        master_entry: Dict[str, Any] = {
            "parent": {"database_id": master_database_id},
            "properties": {
                "product number": {"number": product_id},
                "product name": {"rich_text": [{"text": {"content": product_name}}]},
                "company": {"rich_text": [{"text": {"content": company}}]},
                "product info":{"title": [{"text": {"content": product_info}}]},
                "where": {"multi_select": [{"name": storage} for storage in storages]},
                "note" : {"rich_text": [{"text": {"content": note}}]},
            }
        }
        if image_url:
            master_entry["properties"]["image"] = {"files": [{"name": product_name, "external": {"url": image_url}}]}
#{"object":"error","status":400,"code":"validation_error","message":"body failed validation. Fix one:\nbody.properties.image.files[0].file should be defined, instead was undefined.\nbody.properties.image.files[0].external should be defined, instead was undefined.","request_id":"65ea67dc-dcac-4cd2-ad2e-7680760a5961"}
            # master_entry = {
#             "parent": {"database_id": zaiko_database_id},
#             "properties": {
#                 "product number": {"number": product_number},
#                 "product name": {"title": [{"text": {"content": product_name}}]},
#                 "unit per box": {"number": unit_per_box},
#                 "company": {"title": [{"text": {"content": company}}]},
#                 "product info": {"rich_text": [{"text": {"content": product_info}}]},
#                 "where" : { "multi_select": [{"name": storages}]},
#                 "image": {"files": [{"name": product_image, "url": product_image}]},
#                 "note" : {"rich_text": [{"text": {"content": "note"}}]},
#             }
#         }
        response = requests.post(
                "https://api.notion.com/v1/pages", 
                headers=headers, 
                data=json.dumps(master_entry),
                verify=True,
        )
        if response.status_code == 200:
            st.success(f"マスター登録が完了しました。")
            wait_time = 5
            time.sleep(wait_time)
            st.session_state.step = 'scan'
            st.rerun()
        else:
            st.write(response.text)
            st.error(f"マスター登録に失敗しました。再試行してください。")
            st.session_state.step = 'add_master'
            wait_time = 10
            time.sleep(wait_time)
            st.rerun()

    if st.button("キャンセル"):
        st.session_state.step = 'scan'
        st.rerun()

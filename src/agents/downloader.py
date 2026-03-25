import os
import requests
import zipfile
from datetime import datetime

# Configurações do Sourcing (TSE 2024)
URL_CANDIDATOS = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip"
RAW_DIR = "n888n/data/raw/tse_2024"

class AioxDownloader:
    """Agent: @aiox_downloader
    Responsabilidade: Baixar e extrair arquivos brutos do TSE.
    """
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def download_candidatos(self):
        print(f"🚀 [@aiox_downloader] Iniciando download: {URL_CANDIDATOS}")
        response = requests.get(URL_CANDIDATOS, stream=True)
        
        if response.status_code == 200:
            file_path = os.path.join(self.output_dir, "consulta_cand_2024.zip")
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"✅ [@aiox_downloader] Download concluído: {file_path}")
            return file_path
        else:
            print(f"❌ [@aiox_downloader] Falha no download. Status: {response.status_code}")
            return None

    def extract_zip(self, zip_path):
        print(f"📂 [@aiox_downloader] Extraindo arquivos em {self.output_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.output_dir)
        print("✅ [@aiox_downloader] Extração concluída.")

if __name__ == "__main__":
    downloader = AioxDownloader(RAW_DIR)
    zip_p = downloader.download_candidatos()
    if zip_p:
        downloader.extract_zip(zip_p)

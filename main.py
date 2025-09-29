import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import json
from datetime import datetime
import random 
import pandas as pd
# Gelişmiş PDF için ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from ttkthemes import ThemedTk 

# --- 0. Sabitler ve Güvenilir Veritabanı Fonksiyonları ---

DB_NAME = "stok_takip.db"
SETTINGS_FILE = "settings.json"

# ReportLab için Türkçe karakter desteği
try:
    # Lütfen bilgisayarınızda bir Türkçe font dosyası olduğundan emin olun
    FONT_PATH = "arial.ttf" # Eğer hata alırsanız, bu dosya adını kontrol edin!
    pdfmetrics.registerFont(TTFont('Turu', FONT_PATH))
    FONT_NAME = 'Turu'
except:
    print("ReportLab Türkçe Font Hatası: Arial.ttf bulunamadı. Varsayılan font kullanılacak.")
    FONT_NAME = 'Helvetica'

# Hata Düzeltme Fonksiyonu: Fiyat formatlama sorununu çözer.
def clean_numeric_input(value):
    """Gelen değeri temizler ve float'a dönüştürür. Hata: sqlite3.InterfaceError çözücü."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0

    # Hem virgül hem de nokta kabul edilir ve noktaya çevrilir.
    cleaned_value = value.strip().replace(',', '.')
    
    # Birden fazla nokta varsa (ör: 1.000.00) sadece sonuncuyu bırak
    parts = cleaned_value.rsplit('.', 1)
    if len(parts) == 2:
        cleaned_value = parts[0].replace('.', '') + '.' + parts[1]
    
    try:
        return float(cleaned_value)
    except ValueError:
        return 0.0


def get_db_connection():
    """SQLite bağlantısını döndürür."""
    try:
        return sqlite3.connect(DB_NAME)
    except sqlite3.Error as e:
        messagebox.showerror("Veritabanı Bağlantı Hatası", f"Veritabanına bağlanılamadı: {e}")
        raise

def setup_database():
    """Veritabanını ve gerekli tabloları oluşturur ve ŞEMA'yı günceller."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # TÜM GEREKLİ TABLOLARIN OLUŞTURULMASI
        # purchase_price'ın burada olduğundan emin olun
        cursor.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, stock_quantity INTEGER DEFAULT 0,
            sale_price REAL DEFAULT 0.0, low_stock_threshold INTEGER DEFAULT 10, purchase_price REAL DEFAULT 0.0 
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, type TEXT DEFAULT 'Perakende', balance REAL DEFAULT 0.0
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_number TEXT NOT NULL, customer_id INTEGER, sale_date TEXT, total_amount REAL
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS ledger_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, type TEXT, amount REAL, transaction_date TEXT, description TEXT
        )""")
        
        # KRİTİK DÜZELTME: Eski DB'lerde eksik olan sütunu otomatik olarak ekle
        try:
            cursor.execute("SELECT purchase_price FROM products LIMIT 1")
        except sqlite3.OperationalError:
            # Sütun eksikse ekle (ALTER TABLE)
            cursor.execute("ALTER TABLE products ADD COLUMN purchase_price REAL DEFAULT 0.0")
            print("Veritabanı şeması güncellendi: 'purchase_price' sütunu eklendi.")

        # Örnek Veri Ekleme (UX için)
        if cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            sample_products = [
                ("Laptop Soğutucu", 55, 249.90, 10, 150.00),
                ("Kablosuz Mouse", 8, 99.90, 20, 45.00),
            ]
            cursor.executemany("INSERT INTO products (name, stock_quantity, sale_price, low_stock_threshold, purchase_price) VALUES (?, ?, ?, ?, ?)", sample_products)
        
        if cursor.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
            cursor.execute("INSERT INTO customers (id, name, type) VALUES (?, ?, ?)", (1, "Perakende Müşteri", "Perakende"))
            
        conn.commit()

    except sqlite3.Error as e:
        messagebox.showerror("KRİTİK Veritabanı Hatası", f"Veritabanı kurulumu/güncellemesi başarısız oldu: {e}")
        raise
    finally:
        if conn:
            conn.close()

# ... (Geri kalan tüm sınıflar ve fonksiyonlar aynı kalacak) ...
# Sadece ProductTab ve SalesTab içindeki önemli kısımları tekrardan ekliyorum.

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"company_name": "Şirket Adınız", "pdf_save_path": os.path.expanduser("~/Documents/StokTakipPDFs")}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

def generate_invoice_number():
    date_str = datetime.now().strftime("%Y%m%d")
    random_num = random.randint(10000, 99999)
    return f"TR-{date_str}-{random_num}"


# --- 1. Dashboard Modülü (Değişiklik Yok) ---

class DashboardTab(ttk.Frame):
    """Kontrol Paneli Sekmesi."""
    def __init__(self, master):
        super().__init__(master, padding="15")
        self.pack(expand=True, fill="both")
        self.create_widgets()
        
    def create_widgets(self):
        metrics_frame = ttk.Frame(self)
        metrics_frame.pack(fill='x', pady=10)
        
        self.cards = {}
        card_data = [
            ("Bugün Satış (₺)", "today_sales", "blue"),
            ("Toplam Ürün Çeşidi", "total_products", "green"),
            ("Toplam Cari Açık (₺)", "total_debt", "red"),
        ]
        
        for i, (title, key, color) in enumerate(card_data):
            card = ttk.LabelFrame(metrics_frame, text=title, padding="10")
            card.grid(row=0, column=i, padx=10, pady=5, sticky="nsew")
            metrics_frame.grid_columnconfigure(i, weight=1)
            
            self.cards[key] = ttk.Label(card, text="Yükleniyor...", font=('Arial', 18, 'bold'), foreground=color)
            self.cards[key].pack(expand=True, fill='both')

        ttk.Label(self, text="⚠️ DÜŞÜK STOK UYARILARI", font=('Arial', 14, 'bold'), foreground="red").pack(pady=(20, 5), anchor='w')
        
        columns = ("id", "name", "stock", "threshold")
        self.low_stock_tree = ttk.Treeview(self, columns=columns, show="headings", height=5)
        self.low_stock_tree.heading("name", text="Ürün Adı")
        self.low_stock_tree.heading("stock", text="Mevcut Stok")
        self.low_stock_tree.heading("threshold", text="Eşik Değeri")
        self.low_stock_tree.column("id", width=0, stretch=tk.NO)
        self.low_stock_tree.column("name", width=400, anchor=tk.W)
        self.low_stock_tree.column("stock", width=150, anchor=tk.CENTER)
        self.low_stock_tree.column("threshold", width=150, anchor=tk.CENTER)
        self.low_stock_tree.pack(fill='x')
        self.low_stock_tree.tag_configure('low_alert', background='#FFCCCC')

    def load_stats(self):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            today = datetime.now().strftime("%Y-%m-%d")
            today_sales = cursor.execute("SELECT SUM(total_amount) FROM sales WHERE sale_date LIKE ?", (f'{today}%',)).fetchone()[0] or 0.0
            self.cards['today_sales'].config(text=f"₺{today_sales:.2f}")

            total_products = cursor.execute("SELECT COUNT(id) FROM products").fetchone()[0]
            self.cards['total_products'].config(text=str(total_products))
            
            total_debt = cursor.execute("SELECT SUM(ABS(balance)) FROM customers WHERE balance < 0").fetchone()[0] or 0.0
            self.cards['total_debt'].config(text=f"₺{total_debt:.2f}")
            
            for item in self.low_stock_tree.get_children():
                self.low_stock_tree.delete(item)
                
            low_stock_query = "SELECT id, name, stock_quantity, low_stock_threshold FROM products WHERE stock_quantity <= low_stock_threshold ORDER BY stock_quantity ASC"
            low_stock_rows = cursor.execute(low_stock_query).fetchall()
            
            for row in low_stock_rows:
                self.low_stock_tree.insert("", tk.END, values=row, tags=('low_alert',))
                
        except sqlite3.Error as e:
            messagebox.showerror("DB Hatası", f"İstatistikler yüklenemedi: {e}")
        finally:
            conn.close()


# --- 2. Ürün Yönetimi Modülü ---
class ProductFormWindow(tk.Toplevel):
    def __init__(self, master_tab, product_data=None):
        super().__init__(master_tab)
        self.master_tab = master_tab
        self.product_data = product_data
        self.is_edit = product_data is not None
        
        self.title("Ürün Düzenle" if self.is_edit else "Yeni Ürün Ekle")
        self.transient(master_tab.winfo_toplevel()) 
        self.grab_set() 
        self.create_form()
    
    def create_form(self):
        form_frame = ttk.Frame(self, padding="15")
        form_frame.pack(expand=True, fill="both")
        
        fields = [
            ("Ürün Adı:", "name", ""),
            ("Stok Miktarı:", "stock_quantity", 0),
            ("Alış Fiyatı (₺):", "purchase_price", 0.00), 
            ("Satış Fiyatı (₺):", "sale_price", 0.00),
            ("Düşük Stok Eşiği:", "low_stock_threshold", 10),
        ]
        
        self.entries = {}
        for i, (label_text, key, default_value) in enumerate(fields):
            ttk.Label(form_frame, text=label_text).grid(row=i, column=0, padx=5, pady=5, sticky="w")
            entry = ttk.Entry(form_frame, width=30)
            entry.grid(row=i, column=1, padx=5, pady=5, sticky="ew")
            
            initial_value = self.product_data.get(key, default_value) if self.is_edit else default_value
            if isinstance(initial_value, float) or ('price' in key and self.is_edit):
                 # Virgül ile göstermek için formatlama
                 entry.insert(0, f"{clean_numeric_input(initial_value):.2f}".replace('.', ','))
            else:
                entry.insert(0, str(initial_value))

            self.entries[key] = entry
            
        ttk.Button(form_frame, text="Kaydet", command=self.save_product).grid(row=len(fields), column=0, columnspan=2, pady=20)

    def save_product(self):
        data = {key: entry.get() for key, entry in self.entries.items()}
        
        # HATA DÜZELTMESİ: clean_numeric_input fonksiyonu ile güvenli dönüşüm
        try:
            data['stock_quantity'] = int(data['stock_quantity'])
            data['purchase_price'] = clean_numeric_input(data['purchase_price']) # KRİTİK DÜZELTME
            data['sale_price'] = clean_numeric_input(data['sale_price'])         # KRİTİK DÜZELTME
            data['low_stock_threshold'] = int(data['low_stock_threshold'])
        except ValueError:
            messagebox.showerror("Hata", "Stok ve Eşik alanları geçerli tam sayı, Fiyat alanları geçerli sayı olmalıdır.")
            return
            
        if data['purchase_price'] == 0.0 and data['sale_price'] == 0.0 and messagebox.askyesno("Uyarı", "Alış ve satış fiyatları sıfır. Devam etmek istiyor musunuz?"):
            pass
        elif data['purchase_price'] == 0.0 or data['sale_price'] == 0.0:
            if not messagebox.askyesno("Uyarı", "Alış veya satış fiyatlarından biri sıfır. Yine de kaydetmek istiyor musunuz?"):
                return
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            if self.is_edit:
                query = "UPDATE products SET name=?, stock_quantity=?, sale_price=?, low_stock_threshold=?, purchase_price=? WHERE id=?"
                params = (data['name'], data['stock_quantity'], data['sale_price'], data['low_stock_threshold'], data['purchase_price'], self.product_data['id'])
                cursor.execute(query, params)
            else:
                query = "INSERT INTO products (name, stock_quantity, sale_price, low_stock_threshold, purchase_price) VALUES (?, ?, ?, ?, ?)"
                params = (data['name'], data['stock_quantity'], data['sale_price'], data['low_stock_threshold'], data['purchase_price'])
                cursor.execute(query, params)

            conn.commit()
            self.master_tab.load_products() 
            self.destroy()
            
        except sqlite3.Error as e:
            messagebox.showerror("DB Hatası", f"Ürün kaydedilirken hata oluştu: {e}")
        finally:
            conn.close()

class ProductTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding="10")
        self.pack(expand=True, fill="both")
        self.create_widgets()
        self.load_products()
    
    def create_widgets(self):
        control_frame = ttk.Frame(self)
        control_frame.pack(fill='x', pady=5)
        
        ttk.Label(control_frame, text="🔍 Ürün Ara:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = ttk.Entry(control_frame, width=50)
        self.search_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 20))
        self.search_entry.bind('<KeyRelease>', self.filter_products)
        
        ttk.Button(control_frame, text="✚ Yeni Ürün Ekle", command=lambda: ProductFormWindow(self)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="✏️ Seçileni Düzenle", command=self.open_edit_product_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="🗑️ Seçileni Sil", command=self.delete_product).pack(side=tk.LEFT, padx=5)

        columns = ("id", "name", "stock", "purchase_price", "sale_price", "threshold")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("id", text="ID"); self.tree.column("id", width=50, anchor=tk.CENTER)
        self.tree.heading("name", text="Ürün Adı"); self.tree.column("name", width=250, anchor=tk.W)
        self.tree.heading("stock", text="Stok"); self.tree.column("stock", width=70, anchor=tk.CENTER)
        self.tree.heading("purchase_price", text="Alış (₺)"); self.tree.column("purchase_price", width=80, anchor=tk.E)
        self.tree.heading("sale_price", text="Satış (₺)"); self.tree.column("sale_price", width=80, anchor=tk.E)
        self.tree.heading("threshold", text="Eşik"); self.tree.column("threshold", width=70, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(expand=True, fill="both")
        
        self.tree.tag_configure('low', background='#FFCCCC', foreground='black') 

    def load_products(self, filter_text=""):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Artık purchase_price sütununun var olduğundan eminiz.
            query = "SELECT id, name, stock_quantity, purchase_price, sale_price, low_stock_threshold FROM products WHERE name LIKE ? ORDER BY id DESC"
            cursor.execute(query, ('%' + filter_text + '%',))
            rows = cursor.fetchall()
            
            for row in rows:
                product_id, name, stock, purchase, sale, threshold = row
                tag = 'low' if stock <= threshold else ''
                
                self.tree.insert("", tk.END, 
                                 values=(product_id, name, stock, f"{purchase:.2f}", f"{sale:.2f}", threshold), 
                                 tags=(tag,))
        except sqlite3.Error as e:
            messagebox.showerror("DB Hatası", f"Ürünler yüklenemedi: {e}")
        finally:
            conn.close()

    def filter_products(self, event):
        self.load_products(self.search_entry.get())

    def open_edit_product_window(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen düzenlemek istediğiniz ürünü seçin.")
            return

        values = self.tree.item(selected_item, 'values')
        
        product_data = {
            'id': values[0], 'name': values[1], 'stock_quantity': values[2], 
            'purchase_price': clean_numeric_input(values[3]), 
            'sale_price': clean_numeric_input(values[4]), 
            'low_stock_threshold': values[5],
        }
        ProductFormWindow(self, product_data)

    def delete_product(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen silmek istediğiniz ürünü seçin.")
            return

        product_id = self.tree.item(selected_item, 'values')[0]
        product_name = self.tree.item(selected_item, 'values')[1]

        if messagebox.askyesno("Onay", f"'{product_name}' adlı ürünü silmek istediğinizden emin misiniz?"):
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
                conn.commit()
                self.load_products()
                self.master.master.nametowidget(self.master.winfo_parent()).dashboard_frame.load_stats() 
            except sqlite3.Error as e:
                messagebox.showerror("DB Hatası", f"Ürün silinirken hata oluştu: {e}")
            finally:
                conn.close()


# --- 3. Satış İşlemleri Modülü ---

class SalesTab(ttk.Frame):
    """Hızlı Kasa Sistemi ve Satış Kaydı."""
    def __init__(self, master):
        super().__init__(master, padding="15")
        self.pack(expand=True, fill="both")
        
        self.current_cart = {}  # Sepet içeriği
        self.selected_customer_id = 1 
        self.selected_customer_name = "Perakende Müşteri"
        self.create_widgets()
        self.refresh_cart_display() 

    def create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', pady=(0, 10))
        
        # Müşteri Seçimi Paneli 
        left_panel = ttk.LabelFrame(top_frame, text="👥 Müşteri Seçimi", padding="10")
        left_panel.pack(side=tk.LEFT, padx=10, fill='y')
        
        ttk.Label(left_panel, text="Müşteri:").pack(anchor='w', pady=(0, 5))
        self.customer_var = tk.StringVar()
        self.customer_combo = ttk.Combobox(left_panel, textvariable=self.customer_var, state="readonly", width=30)
        self.customer_combo.pack(anchor='w', pady=(0, 5))
        self.customer_combo.bind('<<ComboboxSelected>>', self.on_customer_selected)
        self.load_customer_combo()
        
        # Yeni Müşteri Ekle Butonu
        ttk.Button(left_panel, text="➕ Yeni Müşteri Ekle", command=self.open_add_customer_window).pack(anchor='w', pady=5)

        # Ürün Arama
        center_panel = ttk.LabelFrame(top_frame, text="🛒 Ürün Ekle", padding="10")
        center_panel.pack(side=tk.LEFT, padx=10, fill='both', expand=True)

        ttk.Label(center_panel, text="Barkod / Ürün Adı Arama (Enter ile Ekle):").pack(anchor='w', pady=(0, 5))
        self.product_search_entry = ttk.Entry(center_panel, width=50, font=('Arial', 12))
        self.product_search_entry.pack(fill='x', pady=(0, 10))
        self.product_search_entry.bind('<Return>', self.add_product_to_cart_by_search)
        
        # Kasa Butonları
        right_panel = ttk.LabelFrame(top_frame, text="💳 Kasa İşlemleri", padding="10")
        right_panel.pack(side=tk.RIGHT, fill='y', padx=10)
        
        ttk.Button(right_panel, text="✅ SATIŞI TAMAMLA", style='Accent.TButton', command=self.complete_sale).pack(fill='x', pady=(0, 15))
        ttk.Button(right_panel, text="❌ Sepeti Temizle", command=self.clear_cart).pack(fill='x', pady=5)
        
        self.create_cart_tree()

    def open_add_customer_window(self):
        app_root = self.master.master.nametowidget(self.master.winfo_parent())
        # CustomerFormWindow'un bu dosyada tanımlı olduğunu varsayıyoruz
        CustomerFormWindow(app_root.customer_frame, master_tab_sales=self) 

    def load_customer_combo(self):
        conn = get_db_connection()
        customers = conn.execute("SELECT id, name, balance FROM customers ORDER BY name ASC").fetchall()
        conn.close()
        
        self.customer_map = {}
        combo_values = []
        default_name = "Perakende Müşteri (N/A)"
        
        for c_id, name, balance in customers:
            balance_tag = 'B' if balance < 0 else ('A' if balance > 0 else 'N/A')
            display_name = f"{name} ({'₺' + f'{abs(balance):.2f}'} {balance_tag})"
            
            combo_values.append(display_name)
            self.customer_map[display_name] = {'id': c_id, 'name': name, 'balance': balance}
            if c_id == 1:
                default_name = display_name
                
        self.customer_combo['values'] = combo_values
        self.customer_var.set(default_name)
        self.selected_customer_id = 1
        self.selected_customer_name = "Perakende Müşteri"

    def on_customer_selected(self, event):
        selected_display = self.customer_var.get()
        if selected_display in self.customer_map:
            data = self.customer_map[selected_display]
            self.selected_customer_id = data['id']
            self.selected_customer_name = data['name']
        
    def create_cart_tree(self):
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill='both', expand=True, pady=10)
        
        columns = ("id", "name", "qty", "unit_price", "total")
        self.cart_tree = ttk.Treeview(bottom_frame, columns=columns, show="headings", selectmode="browse")
        
        self.cart_tree.heading("name", text="Ürün Adı")
        self.cart_tree.heading("qty", text="Adet")
        self.cart_tree.heading("unit_price", text="Birim Fiyat (₺)")
        self.cart_tree.heading("total", text="Toplam (₺)")
        
        self.cart_tree.column("id", width=0, stretch=tk.NO)
        self.cart_tree.column("name", width=350, anchor=tk.W)
        self.cart_tree.column("qty", width=70, anchor=tk.CENTER)
        self.cart_tree.column("unit_price", width=120, anchor=tk.E)
        self.cart_tree.column("total", width=150, anchor=tk.E)
        
        self.cart_tree.pack(side=tk.LEFT, fill="both", expand=True)
        self.cart_tree.bind('<Delete>', self.remove_selected_from_cart)

        summary_frame = ttk.Frame(bottom_frame, width=250)
        summary_frame.pack(side=tk.RIGHT, fill='y', padx=(10, 0))

        ttk.Label(summary_frame, text="GENEL TOPLAM", font=('Arial', 14, 'bold')).pack(pady=(10, 5))
        self.lbl_grand_total = ttk.Label(summary_frame, text="₺0.00", font=('Arial', 24, 'bold'), foreground="green")
        self.lbl_grand_total.pack(pady=(5, 20))
        
    # KRİTİK DÜZELTME: Ürün arama mantığı iyileştirildi.
    def add_product_to_cart_by_search(self, event=None):
        search_term = self.product_search_entry.get().strip()
        if not search_term: return

        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT id, name, sale_price, stock_quantity FROM products WHERE name LIKE ? OR id = ? LIMIT 1"
        
        try:
            p_id_search = int(search_term)
        except ValueError:
            p_id_search = -1 
        
        cursor.execute(query, ('%' + search_term + '%', p_id_search))
        product = cursor.fetchone()
        conn.close()

        if not product:
            messagebox.showwarning("Hata", f"'{search_term}' ile eşleşen ürün bulunamadı.")
            self.product_search_entry.delete(0, tk.END)
            return

        p_id, p_name, p_price, p_stock = product
        
        current_qty_in_cart = self.current_cart.get(p_id, {}).get('qty', 0)
        if current_qty_in_cart + 1 > p_stock:
            messagebox.showwarning("Stok Uyarısı", f"'{p_name}' için yeterli stok yok. Mevcut: {p_stock}")
            self.product_search_entry.delete(0, tk.END)
            return
            
        if p_id in self.current_cart:
            self.current_cart[p_id]['qty'] += 1
        else:
            self.current_cart[p_id] = {'id': p_id, 'name': p_name, 'qty': 1, 'price': p_price, 'stock': p_stock}
        
        self.refresh_cart_display()
        self.product_search_entry.delete(0, tk.END)
        self.product_search_entry.focus_set()


    def refresh_cart_display(self):
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
            
        grand_total = 0.0
        
        for p_id, item in self.current_cart.items():
            total = item['qty'] * item['price']
            grand_total += total
            
            self.cart_tree.insert("", tk.END, 
                                  values=(p_id, item['name'], item['qty'], f"{item['price']:.2f}", f"{total:.2f}"))
        
        self.lbl_grand_total.config(text=f"₺{grand_total:.2f}")


    def remove_selected_from_cart(self, event):
        selected_item = self.cart_tree.focus()
        if not selected_item: return

        p_id = int(self.cart_tree.item(selected_item, 'values')[0])
        if p_id in self.current_cart:
            del self.current_cart[p_id]
        self.refresh_cart_display()


    def clear_cart(self):
        if messagebox.askyesno("Onay", "Sepeti tamamen temizlemek istediğinizden emin misiniz?"):
            self.current_cart = {}
            self.refresh_cart_display()

    
    def complete_sale(self):
        """Satış işlemini tamamlar, veritabanına kaydeder ve stokları düşer."""
        if not self.current_cart:
            messagebox.showwarning("Hata", "Sepet boş! Satış kaydedilemez.")
            return

        total_amount = sum(item['qty'] * item['price'] for item in self.current_cart.values())
        invoice_number = generate_invoice_number()
        sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not messagebox.askyesno("Satış Onayı", f"Müşteri: {self.selected_customer_name}\nToplam: ₺{total_amount:.2f}\nSatışı tamamlamak istiyor musunuz?"):
            return

        conn = get_db_connection()
        try:
            conn.execute("BEGIN TRANSACTION")
            cursor = conn.cursor()
            
            # 1. Satış Ana Kaydını Oluştur
            cursor.execute(
                "INSERT INTO sales (invoice_number, customer_id, sale_date, total_amount) VALUES (?, ?, ?, ?)",
                (invoice_number, self.selected_customer_id, sale_date, total_amount)
            )
            sale_id = cursor.lastrowid
            
            # 2. Stokları Düş
            stock_updates = [(item['qty'], item['id']) for item in self.current_cart.values()]
            cursor.executemany("UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?", stock_updates)

            # 3. Cari Hareket (Perakende müşteri hariç)
            if self.selected_customer_id != 1:
                cursor.execute(
                    "INSERT INTO ledger_transactions (customer_id, type, amount, transaction_date, description) VALUES (?, ?, ?, ?, ?)",
                    (self.selected_customer_id, "Satış", total_amount, sale_date, f"Fatura No: {invoice_number}")
                )
                # Bakiye Güncelleme: Müşteri bize borçlandı (Bakiye negatifleşir/negatife yaklaşır).
                cursor.execute(
                    "UPDATE customers SET balance = balance - ? WHERE id = ?",
                    (total_amount, self.selected_customer_id)
                )

            conn.commit()
            
            messagebox.showinfo("Başarılı", f"Satış kaydedildi! Fatura No: {invoice_number}")
            
            # PDF Fatura Oluşturma (Geliştirilmiş)
            self.create_pdf_invoice(invoice_number, self.selected_customer_name, total_amount, self.current_cart)
            
            # Temizle ve Yenile
            self.clear_cart()
            self.load_customer_combo() 
            app_root = self.master.master.nametowidget(self.master.winfo_parent())
            app_root.product_frame.load_products() 
            app_root.dashboard_frame.load_stats()
            app_root.ledger_frame.load_customer_list() 


        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Satış işlemi sırasında bir hata oluştu: {e}\nİşlem Geri Alındı.")
        finally:
            conn.close()

    def create_pdf_invoice(self, invoice_number, customer_name, total_amount, cart_data):
        """ReportLab ile gerçek PDF faturası oluşturur."""
        import webbrowser
        settings = load_settings()
        pdf_dir = settings['pdf_save_path']
        
        try:
            os.makedirs(pdf_dir, exist_ok=True)
            pdf_path = os.path.join(pdf_dir, f"Fatura_{invoice_number}.pdf")
            
            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            
            c.setFont(FONT_NAME, 20)
            c.drawString(50, height - 50, settings['company_name'])
            
            c.setFont(FONT_NAME, 12)
            c.drawString(50, height - 80, "--- FATURA ---")
            c.drawString(50, height - 100, f"Fatura No: {invoice_number}")
            c.drawString(50, height - 120, f"Müşteri: {customer_name}")
            c.drawString(50, height - 140, f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Tablo Başlıkları
            y_pos = height - 180
            c.setFont(FONT_NAME, 10)
            c.drawString(50, y_pos, "Ürün Adı")
            c.drawString(300, y_pos, "Adet")
            c.drawString(380, y_pos, "Birim Fiyat (₺)")
            c.drawString(500, y_pos, "Toplam (₺)")
            
            c.line(40, y_pos - 5, width - 40, y_pos - 5)
            
            # Ürün Listesi
            y_pos -= 20
            for item in cart_data.values():
                c.drawString(50, y_pos, item['name'][:40])
                c.drawString(300, y_pos, str(item['qty']))
                c.drawString(380, y_pos, f"{item['price']:.2f}")
                c.drawString(500, y_pos, f"{item['qty'] * item['price']:.2f}")
                y_pos -= 15
                if y_pos < 100: # Yeni Sayfa
                    c.showPage()
                    y_pos = height - 50
                    c.setFont(FONT_NAME, 10)
            
            # Toplam
            c.line(450, 70, 580, 70)
            c.setFont(FONT_NAME, 14)
            c.drawString(380, 50, "GENEL TOPLAM:")
            c.drawString(500, 50, f"₺{total_amount:.2f}")
            
            c.save()
            webbrowser.open(pdf_path)
            
        except Exception as e:
            messagebox.showwarning("PDF Hatası", f"PDF dosyası oluşturulamadı. Lütfen 'arial.ttf' dosyasının bulunduğundan ve ReportLab'ın doğru kurulduğundan emin olun: {e}")


# --- 4. Müşteri Yönetimi Modülü (CustomerFormWindow ve CustomerTab) ---

class CustomerFormWindow(tk.Toplevel):
    def __init__(self, master_tab, customer_data=None, master_tab_sales=None):
        super().__init__(master_tab)
        self.master_tab = master_tab
        self.master_tab_sales = master_tab_sales
        self.customer_data = customer_data
        self.is_edit = customer_data is not None
        
        self.title("Müşteri Düzenle" if self.is_edit else "Yeni Müşteri Ekle")
        self.transient(master_tab.winfo_toplevel()) 
        self.grab_set() 
        
        self.create_form()

    def create_form(self):
        form_frame = ttk.Frame(self, padding="15")
        form_frame.pack(expand=True, fill="both")
        
        ttk.Label(form_frame, text="Müşteri Adı:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_name = ttk.Entry(form_frame, width=30)
        self.entry_name.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        ttk.Label(form_frame, text="Müşteri Tipi:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.type_var = tk.StringVar(self)
        self.type_combo = ttk.Combobox(form_frame, textvariable=self.type_var, values=["Perakende", "Toptancı"], state="readonly")
        self.type_combo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        if self.is_edit:
            self.entry_name.insert(0, self.customer_data['name'])
            self.type_var.set(self.customer_data.get('type', 'Perakende'))
        else:
            self.type_var.set("Perakende")
            
        ttk.Button(form_frame, text="Kaydet", command=self.save_customer).grid(row=2, column=0, columnspan=2, pady=20)

    def save_customer(self):
        name = self.entry_name.get().strip()
        customer_type = self.type_var.get()
        
        if not name:
            messagebox.showwarning("Uyarı", "Müşteri Adı boş olamaz.")
            return
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            if self.is_edit:
                query = "UPDATE customers SET name=?, type=? WHERE id=?"
                params = (name, customer_type, self.customer_data['id'])
                cursor.execute(query, params)
            else:
                query = "INSERT INTO customers (name, type) VALUES (?, ?)"
                params = (name, customer_type)
                cursor.execute(query, params)

            conn.commit()
            self.master_tab.load_customers() 
            
            if self.master_tab_sales:
                 self.master_tab_sales.load_customer_combo()
            
            self.destroy()
            
        except sqlite3.Error as e:
            messagebox.showerror("Veritabanı Hatası", f"Müşteri kaydedilirken hata oluştu: {e}")
        finally:
            conn.close()

class CustomerTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding="10")
        self.pack(expand=True, fill="both")
        self.create_widgets()
        self.load_customers()

    def create_widgets(self):
        control_frame = ttk.Frame(self)
        control_frame.pack(fill='x', pady=5)
        
        ttk.Label(control_frame, text="🔍 Müşteri Ara:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = ttk.Entry(control_frame, width=50)
        self.search_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 20))
        self.search_entry.bind('<KeyRelease>', self.filter_customers)
        
        ttk.Button(control_frame, text="✚ Yeni Müşteri Ekle", command=lambda: CustomerFormWindow(self)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="✏️ Seçileni Düzenle", command=self.open_edit_customer_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="🗑️ Seçileni Sil", command=self.delete_customer).pack(side=tk.LEFT, padx=5)

        columns = ("id", "name", "type", "balance")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("id", text="ID"); self.tree.column("id", width=50, anchor=tk.CENTER)
        self.tree.heading("name", text="Müşteri Adı"); self.tree.column("name", width=300, anchor=tk.W)
        self.tree.heading("type", text="Tip"); self.tree.column("type", width=100, anchor=tk.CENTER)
        self.tree.heading("balance", text="Bakiye (₺)"); self.tree.column("balance", width=150, anchor=tk.E)
        
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(expand=True, fill="both")
        
        self.tree.tag_configure('borclu', background='#FFCCCC', foreground='black') 
        self.tree.tag_configure('alacakli', background='#CCFFCC', foreground='black')

    def load_customers(self, filter_text=""):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT id, name, type, balance FROM customers WHERE id != 1 AND name LIKE ? ORDER BY name ASC"
            cursor.execute(query, ('%' + filter_text + '%',))
            rows = cursor.fetchall()
            
            for row in rows:
                c_id, name, c_type, balance = row
                tag = ''
                
                if balance < 0:
                    tag = 'borclu'
                elif balance > 0:
                    tag = 'alacakli'
                
                balance_label = f"₺{abs(balance):.2f} " + ("BORÇLU" if balance < 0 else ("ALACAKLI" if balance > 0 else "Sıfır"))
                
                self.tree.insert("", tk.END, 
                                 values=(c_id, name, c_type, balance_label), 
                                 tags=(tag,))
        except sqlite3.Error as e:
            messagebox.showerror("DB Hatası", f"Müşteriler yüklenemedi: {e}")
        finally:
            conn.close()

    def filter_customers(self, event):
        self.load_customers(self.search_entry.get())

    def open_edit_customer_window(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen düzenlemek istediğiniz müşteriyi seçin.")
            return

        values = self.tree.item(selected_item, 'values')
        
        customer_data = {
            'id': values[0], 
            'name': values[1], 
            'type': values[2], 
        }
        CustomerFormWindow(self, customer_data)

    def delete_customer(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning("Uyarı", "Lütfen silmek istediğiniz müşteriyi seçin.")
            return

        c_id = self.tree.item(selected_item, 'values')[0]
        c_name = self.tree.item(selected_item, 'values')[1]
        
        if messagebox.askyesno("Onay", f"'{c_name}' adlı müşteriyi silmek istediğinizden emin misiniz? (Tüm hareketler silinecektir!)"):
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM customers WHERE id=?", (c_id,))
                cursor.execute("DELETE FROM sales WHERE customer_id=?", (c_id,)) 
                cursor.execute("DELETE FROM ledger_transactions WHERE customer_id=?", (c_id,)) 
                conn.commit()
                messagebox.showinfo("Başarılı", "Müşteri ve tüm ilişkili kayıtlar başarıyla silindi.")
                self.load_customers()
                
                app_root = self.master.master.nametowidget(self.master.winfo_parent())
                app_root.sales_frame.load_customer_combo()
                app_root.dashboard_frame.load_stats()
                app_root.ledger_frame.load_customer_list() 
            except sqlite3.Error as e:
                messagebox.showerror("Hata", f"Müşteri silinirken hata oluştu: {e}")
            finally:
                conn.close()


# --- 5. Cari İşlemler Modülü (LedgerTransactionWindow ve LedgerTab) ---
class LedgerTransactionWindow(tk.Toplevel):
    def __init__(self, master_tab, customer_id, customer_name, transaction_type):
        super().__init__(master_tab)
        self.master_tab = master_tab
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.transaction_type = transaction_type 
        
        self.title(f"{customer_name} - {transaction_type} Girişi")
        self.transient(master_tab.winfo_toplevel()) 
        self.grab_set() 
        self.create_form()

    def create_form(self):
        form_frame = ttk.Frame(self, padding="15")
        form_frame.pack(expand=True, fill="both")
        
        ttk.Label(form_frame, text=f"{self.transaction_type} Miktarı (₺):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_amount = ttk.Entry(form_frame, width=20)
        self.entry_amount.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        ttk.Label(form_frame, text="Açıklama:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_desc = ttk.Entry(form_frame, width=30)
        self.entry_desc.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        ttk.Button(form_frame, text="Kaydet", command=self.save_transaction).grid(row=2, column=0, columnspan=2, pady=20)

    def save_transaction(self):
        try:
            amount = clean_numeric_input(self.entry_amount.get())
            if amount <= 0: raise ValueError("Miktar pozitif olmalıdır.")
        except ValueError:
            messagebox.showerror("Hata", "Miktar alanı geçerli pozitif bir sayı olmalıdır.")
            return

        description = self.entry_desc.get().strip()
        transaction_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        balance_change = amount if self.transaction_type == "Tahsilat" else -amount

        conn = get_db_connection()
        try:
            conn.execute("BEGIN TRANSACTION")
            
            conn.execute(
                "INSERT INTO ledger_transactions (customer_id, type, amount, transaction_date, description) VALUES (?, ?, ?, ?, ?)",
                (self.customer_id, self.transaction_type, amount, transaction_date, description)
            )
            
            conn.execute(
                "UPDATE customers SET balance = balance + ? WHERE id = ?",
                (balance_change, self.customer_id)
            )

            conn.commit()
            messagebox.showinfo("Başarılı", f"Cari hareket başarıyla kaydedildi.")
            
            self.master_tab.load_customer_info(self.customer_id) 
            self.master_tab.load_transactions(self.customer_id) 
            app_root = self.master_tab.master.nametowidget(self.master_tab.winfo_parent())
            app_root.sales_frame.load_customer_combo()
            app_root.dashboard_frame.load_stats()

            self.destroy()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Hata", f"Cari işlem kaydedilirken hata oluştu: {e}")
        finally:
            conn.close()

class LedgerTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding="10")
        self.pack(expand=True, fill="both")
        self.selected_customer_id = None
        self.selected_customer_name = ""
        self.create_widgets()
        self.load_customer_list()
        
    def create_widgets(self):
        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main_paned, width=300, padding="10")
        main_paned.add(left_frame, weight=0)
        
        ttk.Label(left_frame, text="👥 CARİ MÜŞTERİLER", font=('Arial', 12, 'bold')).pack(fill='x', pady=(0, 5))
        
        self.customer_list_tree = ttk.Treeview(left_frame, columns=("id", "name"), show="tree headings", selectmode="browse")
        self.customer_list_tree.heading("name", text="Müşteri Adı")
        self.customer_list_tree.column("id", width=0, stretch=tk.NO)
        self.customer_list_tree.column("#0", width=250, anchor=tk.W)
        
        self.customer_list_tree.pack(expand=True, fill="both")
        self.customer_list_tree.bind('<<TreeviewSelect>>', self.on_customer_select)


        right_frame = ttk.Frame(main_paned, padding="10")
        main_paned.add(right_frame, weight=1)
        
        self.lbl_customer_name = ttk.Label(right_frame, text="Müşteri Seçilmedi", font=('Arial', 14, 'bold'))
        self.lbl_customer_name.pack(anchor='w', pady=(0, 5))
        self.lbl_balance = ttk.Label(right_frame, text="Bakiye: ₺0.00", font=('Arial', 12))
        self.lbl_balance.pack(anchor='w', pady=(0, 10))

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="➕ BORÇ EKLE", command=lambda: self.open_transaction_window("Borç")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="➖ TAHSİLAT GİR", command=lambda: self.open_transaction_window("Tahsilat")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📄 EKSTRE YAZDIR (PDF)", command=self.print_ledger).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(right_frame, text="Cari Hareketler", font=('Arial', 12)).pack(anchor='w', pady=(10, 5))
        columns = ("date", "type", "description", "amount")
        self.ledger_tree = ttk.Treeview(right_frame, columns=columns, show="headings")
        self.ledger_tree.heading("date", text="Tarih")
        self.ledger_tree.heading("type", text="Tip")
        self.ledger_tree.heading("description", text="Açıklama")
        self.ledger_tree.heading("amount", text="Miktar (₺)")
        
        self.ledger_tree.column("date", width=150, anchor=tk.CENTER)
        self.ledger_tree.column("type", width=100, anchor=tk.CENTER)
        self.ledger_tree.column("description", width=300, anchor=tk.W)
        self.ledger_tree.column("amount", width=100, anchor=tk.E)
        
        self.ledger_tree.pack(expand=True, fill="both")

    def load_customer_list(self):
        for item in self.customer_list_tree.get_children():
            self.customer_list_tree.delete(item)
            
        conn = get_db_connection()
        customers = conn.execute("SELECT id, name, balance FROM customers WHERE id != 1 ORDER BY name ASC").fetchall()
        conn.close()
        
        for c_id, name, balance in customers:
            balance_tag = 'B' if balance < 0 else ('A' if balance > 0 else 'N/A')
            display_name = f"{name} ({'₺' + f'{abs(balance):.2f}'} {balance_tag})"
            self.customer_list_tree.insert("", tk.END, iid=c_id, text=display_name, values=(c_id, name))

    def on_customer_select(self, event):
        selected_item = self.customer_list_tree.focus()
        if not selected_item: return
        
        self.selected_customer_id = int(selected_item)
        
        conn = get_db_connection()
        customer = conn.execute("SELECT name FROM customers WHERE id = ?", (self.selected_customer_id,)).fetchone()
        conn.close()
        
        if customer:
            self.selected_customer_name = customer[0]
            self.load_customer_info(self.selected_customer_id)
            self.load_transactions(self.selected_customer_id)

    def load_customer_info(self, c_id):
        conn = get_db_connection()
        customer = conn.execute("SELECT name, balance FROM customers WHERE id = ?", (c_id,)).fetchone()
        conn.close()
        
        if customer:
            name, balance = customer
            self.lbl_customer_name.config(text=name)
            
            balance_text = f"Bakiye: ₺{abs(balance):.2f}"
            if balance < 0:
                self.lbl_balance.config(text=f"{balance_text} BORÇLU (Alacağımız var)", foreground="red")
            elif balance > 0:
                self.lbl_balance.config(text=f"{balance_text} ALACAKLI (Borcumuz var)", foreground="green")
            else:
                self.lbl_balance.config(text="Bakiye: Sıfır", foreground="black")

    def load_transactions(self, c_id):
        for item in self.ledger_tree.get_children():
            self.ledger_tree.delete(item)
            
        conn = get_db_connection()
        query = "SELECT transaction_date, type, description, amount FROM ledger_transactions WHERE customer_id = ? ORDER BY transaction_date DESC"
        transactions = conn.execute(query, (c_id,)).fetchall()
        conn.close()
        
        for date, t_type, desc, amount in transactions:
            self.ledger_tree.insert("", tk.END, values=(date[:16], t_type, desc, f"{amount:.2f}"))

    def open_transaction_window(self, transaction_type):
        if not self.selected_customer_id or self.selected_customer_id == 1:
            messagebox.showwarning("Uyarı", "Lütfen önce cari işlem yapacağınız müşteriyi listeden seçin.")
            return

        LedgerTransactionWindow(self, self.selected_customer_id, self.selected_customer_name, transaction_type)
        
    def print_ledger(self):
        if not self.selected_customer_id or self.selected_customer_id == 1:
            messagebox.showwarning("Uyarı", "Lütfen önce ekstresini almak istediğiniz müşteriyi seçin.")
            return
        
        conn = get_db_connection()
        query = "SELECT transaction_date, type, description, amount FROM ledger_transactions WHERE customer_id = ? ORDER BY transaction_date ASC"
        transactions = conn.execute(query, (self.selected_customer_id,)).fetchall()
        conn.close()
        
        if not transactions:
            messagebox.showwarning("Uyarı", "Bu müşteri için cari hareket bulunmamaktadır.")
            return
            
        settings = load_settings()
        pdf_dir = settings['pdf_save_path']
        
        try:
            os.makedirs(pdf_dir, exist_ok=True)
            pdf_path = os.path.join(pdf_dir, f"Ekstre_{self.selected_customer_name}_{datetime.now().strftime('%Y%m%d')}.pdf")
            
            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            
            c.setFont(FONT_NAME, 16)
            c.drawString(50, height - 50, f"CARİ EKSTRE: {self.selected_customer_name}")
            c.setFont(FONT_NAME, 10)
            c.drawString(50, height - 70, f"Şirket: {settings['company_name']}")
            c.drawString(50, height - 90, f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            
            # Tablo Başlıkları
            y_pos = height - 120
            c.setFont(FONT_NAME, 10)
            c.drawString(50, y_pos, "Tarih")
            c.drawString(180, y_pos, "Tip")
            c.drawString(280, y_pos, "Açıklama")
            c.drawString(500, y_pos, "Miktar (₺)")
            
            c.line(40, y_pos - 5, width - 40, y_pos - 5)
            
            # Hareket Listesi
            y_pos -= 20
            for date, t_type, desc, amount in transactions:
                c.drawString(50, y_pos, date[:16])
                c.drawString(180, y_pos, t_type)
                c.drawString(280, y_pos, desc[:30])
                c.drawString(500, y_pos, f"{amount:.2f}")
                y_pos -= 15
                if y_pos < 50:
                    c.showPage()
                    y_pos = height - 50
                    c.setFont(FONT_NAME, 10)
            
            # Bakiye
            c.line(40, y_pos - 10, width - 40, y_pos - 10)
            c.setFont(FONT_NAME, 12)
            c.drawString(50, y_pos - 30, self.lbl_balance.cget('text'))
            
            c.save()
            import webbrowser
            webbrowser.open(pdf_path)
            
        except Exception as e:
            messagebox.showwarning("Rapor Hatası", f"Ekstre PDF dosyası oluşturulamadı: {e}")


# --- 6. Raporlama Modülü (ReportTab) ---

class ReportTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding="10")
        self.pack(expand=True, fill="both")
        self.create_widgets()

    def create_widgets(self):
        control_frame = ttk.LabelFrame(self, text="Rapor Filtresi", padding="10")
        control_frame.pack(fill='x', pady=10)
        
        ttk.Label(control_frame, text="Başlangıç Tarihi (YYYY-MM-DD):").grid(row=0, column=0, padx=5, pady=5)
        self.start_date_entry = ttk.Entry(control_frame, width=15)
        self.start_date_entry.insert(0, (datetime.now() - pd.DateOffset(months=1)).strftime('%Y-%m-%d'))
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(control_frame, text="Bitiş Tarihi (YYYY-MM-DD):").grid(row=0, column=2, padx=5, pady=5)
        self.end_date_entry = ttk.Entry(control_frame, width=15)
        self.end_date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
        self.end_date_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Rapor Oluştur", command=self.generate_report, style='Accent.TButton').grid(row=0, column=4, padx=15, pady=5)
        ttk.Button(control_frame, text="PDF Olarak Kaydet", command=self.save_report_pdf).grid(row=0, column=5, padx=5, pady=5)
        
        columns = ("invoice", "date", "customer", "total")
        self.report_tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        
        self.report_tree.heading("invoice", text="Fatura No")
        self.report_tree.heading("date", text="Tarih")
        self.report_tree.heading("customer", text="Müşteri")
        self.report_tree.heading("total", text="Toplam (₺)")
        
        self.report_tree.column("invoice", width=150, anchor=tk.CENTER)
        self.report_tree.column("date", width=150, anchor=tk.CENTER)
        self.report_tree.column("customer", width=300, anchor=tk.W)
        self.report_tree.column("total", width=120, anchor=tk.E)
        
        self.report_tree.pack(expand=True, fill="both", pady=10)

        summary_frame = ttk.Frame(self)
        summary_frame.pack(fill='x')
        self.lbl_summary = ttk.Label(summary_frame, text="Toplam Satış: ₺0.00", font=('Arial', 14, 'bold'), foreground="darkorange")
        self.lbl_summary.pack(side=tk.LEFT, padx=10, pady=5)

    def generate_report(self):
        start_date = self.start_date_entry.get()
        end_date = self.end_date_entry.get()
        
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
        except ValueError:
            messagebox.showerror("Hata", "Lütfen tarihleri YYYY-MM-DD formatında girin.")
            return

        for item in self.report_tree.get_children():
            self.report_tree.delete(item)
            
        conn = get_db_connection()
        try:
            query = """
                SELECT s.invoice_number, s.sale_date, c.name, s.total_amount
                FROM sales s
                JOIN customers c ON s.customer_id = c.id
                WHERE s.sale_date BETWEEN ? AND ? || ' 23:59:59' 
                ORDER BY s.sale_date DESC
            """
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            
            total_sales = 0.0
            
            for row in rows:
                invoice, date, customer, total = row
                total_sales += total
                
                self.report_tree.insert("", tk.END, 
                                        values=(invoice, date[:16], customer, f"{total:.2f}"))
            
            self.lbl_summary.config(text=f"TOPLAM SATIŞ ({len(rows)} Adet): ₺{total_sales:.2f}")

        except sqlite3.Error as e:
            messagebox.showerror("DB Hatası", f"Rapor oluşturulurken hata oluştu: {e}")
        finally:
            conn.close()

    def save_report_pdf(self):
        data = []
        for child in self.report_tree.get_children():
            data.append(self.report_tree.item(child, 'values'))
            
        if not data:
            messagebox.showwarning("Uyarı", "Önce bir rapor oluşturmalısınız.")
            return
            
        settings = load_settings()
        pdf_dir = settings['pdf_save_path']
        
        try:
            os.makedirs(pdf_dir, exist_ok=True)
            pdf_path = os.path.join(pdf_dir, f"SatisRaporu_{self.start_date_entry.get()}_{self.end_date_entry.get()}.pdf")
            
            c = canvas.Canvas(pdf_path, pagesize=A4)
            width, height = A4
            
            c.setFont(FONT_NAME, 16)
            c.drawString(50, height - 50, "SATİŞ RAPORU")
            c.setFont(FONT_NAME, 10)
            c.drawString(50, height - 70, f"Şirket: {settings['company_name']}")
            c.drawString(50, height - 90, f"Tarih Aralığı: {self.start_date_entry.get()} - {self.end_date_entry.get()}")
            
            # Tablo Başlıkları
            y_pos = height - 120
            c.setFont(FONT_NAME, 10)
            c.drawString(50, y_pos, "Fatura No")
            c.drawString(180, y_pos, "Tarih")
            c.drawString(350, y_pos, "Müşteri")
            c.drawString(500, y_pos, "Toplam (₺)")
            
            c.line(40, y_pos - 5, width - 40, y_pos - 5)
            
            # Rapor Listesi
            y_pos -= 20
            for invoice, date, customer, total in data:
                c.drawString(50, y_pos, invoice)
                c.drawString(180, y_pos, date)
                c.drawString(350, y_pos, customer[:20])
                c.drawString(500, y_pos, total)
                y_pos -= 15
                if y_pos < 50:
                    c.showPage()
                    y_pos = height - 50
                    c.setFont(FONT_NAME, 10)
            
            # Özet
            c.line(40, y_pos - 10, width - 40, y_pos - 10)
            c.setFont(FONT_NAME, 12)
            c.drawString(50, y_pos - 30, self.lbl_summary.cget('text'))
            
            c.save()
            import webbrowser
            webbrowser.open(pdf_path)
            
        except Exception as e:
            messagebox.showwarning("PDF Hatası", f"Rapor PDF dosyası oluşturulamadı: {e}")


# --- 7. Ana Uygulama Sınıfı (StokTakipApp) ---

class StokTakipApp(ThemedTk):
    def __init__(self):
        super().__init__(theme="arc") 
        self.title("Stok ve Satış Takip Sistemi (Hata Giderildi)")
        self.geometry("1200x800")
        self.state('zoomed')  # Tam ekran (maximized) modunda aç

        # Uygulama ikonu ayarla
        try:
            icon = tk.PhotoImage(file='loading_2482488.png')
            self.iconphoto(True, icon)
        except Exception as e:
            print(f"İkon yüklenirken hata: {e}")

        setup_database() # KRİTİK: DB Şema Kontrolü burada yapılıyor
        self.settings = load_settings()
        
        style = ttk.Style()
        style.configure('Accent.TButton', font=('Arial', 10, 'bold'), foreground='blue') 

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")
        
        self._create_tabs()
        
    def _create_tabs(self):
        
        self.dashboard_frame = DashboardTab(self.notebook)
        self.notebook.add(self.dashboard_frame, text="📈 Kontrol Paneli")

        self.product_frame = ProductTab(self.notebook) 
        self.notebook.add(self.product_frame, text="📦 Ürün Yönetimi")

        self.sales_frame = SalesTab(self.notebook)
        self.notebook.add(self.sales_frame, text="🛒 Satış İşlemleri")
        
        self.customer_frame = CustomerTab(self.notebook)
        self.notebook.add(self.customer_frame, text="👥 Müşteri Yönetimi")

        self.ledger_frame = LedgerTab(self.notebook)
        self.notebook.add(self.ledger_frame, text="💰 Cari İşlemler")
        
        self.report_frame = ReportTab(self.notebook)
        self.notebook.add(self.report_frame, text="📰 Raporlama")

        self.settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_frame, text="⚙️ Ayarlar")
        self._setup_settings_tab()
        
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)


    def _on_tab_change(self, event):
        selected_tab_id = self.notebook.select()
        tab_name = self.notebook.tab(selected_tab_id, "text")

        if "Kontrol Paneli" in tab_name:
            self.dashboard_frame.load_stats()
        elif "Ürün Yönetimi" in tab_name:
            self.product_frame.load_products()
        elif "Müşteri Yönetimi" in tab_name:
            self.customer_frame.load_customers()
        elif "Cari İşlemler" in tab_name:
            self.ledger_frame.load_customer_list() 

    def _setup_settings_tab(self):
        current_settings = self.settings
        tk.Label(self.settings_frame, text="Şirket Bilgileri ve Ayarlar", font=("Arial", 16)).pack(pady=10)

        tk.Label(self.settings_frame, text="Şirket Adı:").pack(anchor='w', padx=20)
        self.entry_company_name = tk.Entry(self.settings_frame, width=50)
        self.entry_company_name.insert(0, current_settings.get("company_name", ""))
        self.entry_company_name.pack(anchor='w', padx=20)
        
        tk.Label(self.settings_frame, text="PDF Kayıt Klasörü:").pack(anchor='w', padx=20, pady=(10,0))
        path_frame = ttk.Frame(self.settings_frame)
        path_frame.pack(anchor='w', padx=20, fill='x')
        self.entry_pdf_path = tk.Entry(path_frame, width=40)
        self.entry_pdf_path.insert(0, current_settings.get("pdf_save_path", ""))
        self.entry_pdf_path.pack(side=tk.LEFT, fill='x', expand=True)
        ttk.Button(path_frame, text="Gözat", command=self._browse_pdf_path).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(self.settings_frame, text="Ayarları Kaydet", command=self._save_settings_action).pack(pady=20, padx=20)

    def _browse_pdf_path(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.entry_pdf_path.delete(0, tk.END)
            self.entry_pdf_path.insert(0, folder_selected)

    def _save_settings_action(self):
        new_settings = {
            "company_name": self.entry_company_name.get(),
            "pdf_save_path": self.entry_pdf_path.get()
        }
        
        save_settings(new_settings)
        self.settings = new_settings 
        messagebox.showinfo("Başarılı", "Ayarlar başarıyla kaydedildi!")


# --- 8. Giriş Ekranı (Splash Screen) ---

class SplashScreen(tk.Toplevel):
    def __init__(self, company_name):
        super().__init__()
        self.overrideredirect(True)  # Kenarlık olmadan
        self.geometry("450x350+500+250")  # Daha büyük ve ortada
        self.configure(bg='#f0f0f0')  # Açık gri arka plan

        # İkon ayarla
        try:
            icon = tk.PhotoImage(file='loading_2482488.png')
            self.iconphoto(True, icon)
        except Exception as e:
            print(f"İkon yüklenirken hata: {e}")

        # Şirket adı
        ttk.Label(self, text=company_name, font=('Arial', 24, 'bold'), background='#f0f0f0', foreground='#2E8B57').pack(pady=20)

        # Yükleme resmi
        try:
            img = tk.PhotoImage(file='loading_2482488.png')
            lbl_img = ttk.Label(self, image=img, background='#f0f0f0')
            lbl_img.pack(pady=10)
            self.img = img  # Referans tut
        except Exception as e:
            print(f"Resim yüklenirken hata: {e}")

        # Yükleniyor mesajı
        self.lbl_status = ttk.Label(self, text="Uygulama Başlatılıyor...", font=('Arial', 14), background='#f0f0f0')
        self.lbl_status.pack(pady=10)

        # İlerleme çubuğu
        self.progress = ttk.Progressbar(self, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=10)

        # Yüzde etiketi
        self.lbl_percent = ttk.Label(self, text="0%", font=('Arial', 12), background='#f0f0f0')
        self.lbl_percent.pack(pady=5)

        self.update()
        self.after(3000, self.destroy)  # 3 saniye sonra kapat


# --- 9. Uygulamayı Çalıştırma ---

if __name__ == "__main__":
    try:
        settings = load_settings()
        app = StokTakipApp()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("KRİTİK HATA", f"Uygulama başlatılırken beklenmedik bir hata oluştu: {e}")

import shutil
import sys
import tempfile
from pathlib import Path

# Imports directly from your 3 helper files
try:
    from ImageFinder import fetch_and_show_vehicle_image
    from LoadoutSearch import (
        build_file_index,
        get_vehicle_weapons,
        load_all_localizations,
    )
    from VehicleLook import (
        auto_find_wt_ext,
        auto_find_wt_path,
        extract_file_details,
        load_nations_from_shop,
        run_wt_ext,
    )
except ImportError as e:
    print(f"[Error] Failed to import modules: {e}")
    print(
        "Ensure VehicleLook.py, LoadoutSearch.py, and ImageFinder.py are in"
        " the same folder."
    )
    sys.exit(1)

from PySide6.QtCore import QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


def classify_vehicle_type(file_path: Path) -> str:
    """Classifies a vehicle file into Planes, Tanks, Helicopters, or Ships."""
    path_str = str(file_path).replace("\\", "/").lower()
    file_stem = file_path.stem.lower()

    if (
        "/tankmodels/" in path_str
        or "/tanks/" in path_str
        or "tank_" in file_stem
    ):
        return "Tanks"
    if "/ships/" in path_str or "/boats/" in path_str or "/navy/" in path_str:
        return "Ships"
    if "/helicopters/" in path_str or file_stem.startswith(
        (
            "ah_",
            "mi_",
            "ka_",
            "uh_",
            "bo_",
            "tiger_",
            "z_",
            "ab_",
            "a_129",
            "eurocopter",
            "hkp",
            "lynx",
            "g_lynx",
            "sa_341",
            "sa_342",
            "wasp",
            "scout",
            "rooivalk",
        )
    ):
        return "Helicopters"

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(2048).lower()
            if (
                'type:t="helicopter"' in content
                or "ishelicopter:b=yes" in content
            ):
                return "Helicopters"
            if 'type:t="tank"' in content or 'vehicletype:t="tank"' in content:
                return "Tanks"
            if 'type:t="ship"' in content or 'type:t="boat"' in content:
                return "Ships"
    except Exception:
        pass

    return "Planes"


class UnifiedExtractor:

    def __init__(self):
        self.wt_dir = auto_find_wt_path()
        self.wt_ext_path = auto_find_wt_ext()
        self.temp_dir = None
        self.names_map = {}
        self.nations_map = {}
        self.file_index = {}

    def initialize(self) -> bool:
        if not self.wt_dir or not self.wt_dir.exists():
            print("[Error] War Thunder installation directory not found.")
            return False

        if not self.wt_ext_path or not self.wt_ext_path.is_file():
            print("[Error] wt_ext_cli.exe not found in application directory.")
            return False

        self.temp_dir = Path(tempfile.mkdtemp(prefix="wt_unified_search_"))

        # Extract all gamedata (Planes, Tanks, Helicopters, Ships)
        run_wt_ext(
            self.wt_ext_path,
            self.wt_dir / "aces.vromfs.bin",
            self.temp_dir,
            folder_subpath="gamedata",
            fmt="BlkText",
        )

        # Extract config
        run_wt_ext(
            self.wt_ext_path,
            self.wt_dir / "char.vromfs.bin",
            self.temp_dir,
            folder_subpath="config",
            fmt="BlkText",
        )

        # Process localizations
        lang_dest = self.temp_dir / "lang"
        if (self.wt_dir / "lang").exists():
            shutil.copytree(self.wt_dir / "lang", lang_dest, dirs_exist_ok=True)
        else:
            run_wt_ext(
                self.wt_ext_path,
                self.wt_dir / "lang.vromfs.bin",
                lang_dest,
                fmt="Raw",
            )

        self.names_map = load_all_localizations(lang_dest)
        self.nations_map = load_nations_from_shop(self.temp_dir)
        self.file_index = build_file_index(self.temp_dir)

        return True

    def cleanup(self):
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


class VehicleExplorerApp(QMainWindow):

    def __init__(self, extractor: UnifiedExtractor):
        super().__init__()
        self.extractor = extractor
        self.current_vid = ""
        self.setWindowTitle("War Thunder Vehicle & Loadout Explorer")
        self.resize(960, 560)

        self.net_manager = QNetworkAccessManager(self)
        self.net_manager.finished.connect(self._on_image_downloaded)

        self._setup_ui()
        self._populate_initial_list()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Filter Bar: Nation + Vehicle Type + Search Text
        filter_layout = QHBoxLayout()

        # Nation Filter Dropdown
        filter_layout.addWidget(QLabel("Nation:"))
        self.combo_nation = QComboBox()
        self.combo_nation.addItems(
            [
                "All Nations",
                "USA",
                "Germany",
                "USSR",
                "Britain",
                "Japan",
                "China",
                "Italy",
                "France",
                "Sweden",
                "Israel",
            ]
        )
        self.combo_nation.currentIndexChanged.connect(self._filter_vehicles)
        filter_layout.addWidget(self.combo_nation)

        # Vehicle Type Filter Dropdown
        filter_layout.addWidget(QLabel("Type:"))
        self.combo_type = QComboBox()
        self.combo_type.addItems(
            ["All Types", "Planes", "Tanks", "Helicopters", "Ships"]
        )
        self.combo_type.currentIndexChanged.connect(self._filter_vehicles)
        filter_layout.addWidget(self.combo_type)

        # Search Box
        filter_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search vehicle name or ID...")
        self.search_input.textChanged.connect(self._filter_vehicles)
        filter_layout.addWidget(self.search_input)

        main_layout.addLayout(filter_layout)

        # Splitter Layout
        splitter = QSplitter()
        main_layout.addWidget(splitter)

        # Left: Vehicle Tree Widget
        self.vehicle_tree = QTreeWidget()
        self.vehicle_tree.setHeaderLabels(
            ["Vehicle Name", "ID", "Nation", "Type"]
        )
        self.vehicle_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.vehicle_tree.itemSelectionChanged.connect(
            self._on_vehicle_selected
        )
        splitter.addWidget(self.vehicle_tree)

        # Right: Vehicle Details Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        form_layout = QFormLayout()
        self.lbl_name = QLabel("N/A")
        self.lbl_id = QLabel("N/A")
        self.lbl_nation = QLabel("N/A")
        self.lbl_type = QLabel("N/A")
        self.lbl_model_id = QLabel("N/A")

        form_layout.addRow("Display Name:", self.lbl_name)
        form_layout.addRow("Vehicle ID:", self.lbl_id)
        form_layout.addRow("Nation:", self.lbl_nation)
        form_layout.addRow("Type:", self.lbl_type)
        form_layout.addRow("Model ID:", self.lbl_model_id)

        self.combo_loadout = QComboBox()
        form_layout.addRow("Available Weapons:", self.combo_loadout)

        right_layout.addLayout(form_layout)

        # Image Preview Box
        self.img_preview = QLabel("Select a vehicle to load preview")
        self.img_preview.setStyleSheet(
            "border: 1px solid #444; background: #1a1a1a;"
        )
        self.img_preview.setFixedSize(380, 215)
        self.img_preview.setScaledContents(True)
        right_layout.addWidget(self.img_preview)

        right_layout.addStretch()
        splitter.addWidget(right_panel)
        splitter.setSizes([420, 540])

    def _populate_initial_list(self):
        self.all_vehicles = []
        seen_stems = set()

        # Gather unit files across flightmodels, tankmodels, helicopters, and ships
        for fpath in self.extractor.temp_dir.rglob("*"):
            if not fpath.is_file() or fpath.suffix.lower() not in [
                ".blk",
                ".blkx",
            ]:
                continue

            rel_str = str(fpath).replace("\\", "/").lower()

            # Skip weapon/preset/config subfolders when collecting vehicles
            if any(
                x in rel_str
                for x in [
                    "/weaponry/",
                    "/weapons/",
                    "/config/",
                    "/lang/",
                    "/fx/",
                    "/templates/",
                ]
            ):
                continue

            if any(
                x in rel_str
                for x in [
                    "flightmodels/",
                    "tankmodels/",
                    "tanks/",
                    "helicopters/",
                    "ships/",
                ]
            ):
                vid = fpath.stem.lower()

                # Avoid duplicate entries or presets
                if vid in seen_stems or vid.endswith("_default"):
                    continue
                seen_stems.add(vid)

                disp_name = (
                    self.extractor.names_map.get(vid)
                    or self.extractor.names_map.get(vid.replace("_", "-"))
                    or self.extractor.names_map.get(f"{vid}_shop")
                    or vid
                )

                model_id, file_nation = extract_file_details(fpath)
                nation = (
                    self.extractor.nations_map.get(vid)
                    or self.extractor.nations_map.get(vid.replace("_", "-"))
                    or file_nation
                )

                vtype = classify_vehicle_type(fpath)

                self.all_vehicles.append(
                    {
                        "id": vid,
                        "name": disp_name,
                        "model_id": model_id,
                        "nation": nation,
                        "type": vtype,
                        "path": fpath,
                    }
                )

        self.all_vehicles.sort(key=lambda x: x["name"])
        self._filter_vehicles()

    def _filter_vehicles(self):
        selected_nation = self.combo_nation.currentText()
        selected_type = self.combo_type.currentText()
        query = self.search_input.text().strip().lower()

        self.vehicle_tree.clear()

        for v in self.all_vehicles:
            nation_match = (
                selected_nation == "All Nations"
                or v["nation"].lower() == selected_nation.lower()
            )
            type_match = (
                selected_type == "All Types"
                or v["type"].lower() == selected_type.lower()
            )

            text_match = (
                not query
                or query in v["id"]
                or query in v["id"].replace("_", "-")
                or query in v["name"].lower()
            )

            if nation_match and type_match and text_match:
                item = QTreeWidgetItem(
                    [v["name"], v["id"], v["nation"], v["type"]]
                )
                item.setData(0, 256, v)
                self.vehicle_tree.addTopLevelItem(item)

    def _on_vehicle_selected(self):
        selected = self.vehicle_tree.selectedItems()
        if not selected:
            return

        v_data = selected[0].data(0, 256)
        vid = v_data["id"]
        self.current_vid = vid

        self.lbl_name.setText(v_data["name"])
        self.lbl_id.setText(vid)
        self.lbl_nation.setText(v_data["nation"])
        self.lbl_type.setText(v_data["type"])
        self.lbl_model_id.setText(v_data["model_id"])

        # Fetch unwrapped weapons
        weapons = get_vehicle_weapons(
            vid, self.extractor.names_map, self.extractor.file_index
        )
        self.combo_loadout.clear()

        if weapons:
            for name, w_id in weapons:
                self.combo_loadout.addItem(f"{name} ({w_id})", w_id)
        else:
            self.combo_loadout.addItem("No mounted weapons found")

        # Request CDN preview image
        self.img_preview.setText("Loading image...")
        cdn_url = f"https://static.encyclopedia.warthunder.com/images/{vid}.png"

        req = QNetworkRequest(QUrl(cdn_url))
        req.setRawHeader(
            b"User-Agent",
            b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0",
        )
        self.net_manager.get(req)

    def _on_image_downloaded(self, reply):
        if reply.error() == reply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                self.img_preview.setPixmap(pixmap)
            else:
                self.img_preview.setText("Image unavailable")
        else:
            if "_" in self.current_vid:
                hyphen_id = self.current_vid.replace("_", "-")
                fallback_url = f"https://static.encyclopedia.warthunder.com/images/{hyphen_id}.png"
                self.current_vid = hyphen_id
                req = QNetworkRequest(QUrl(fallback_url))
                req.setRawHeader(
                    b"User-Agent",
                    b"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    b" Chrome/115.0.0.0",
                )
                self.net_manager.get(req)
                reply.deleteLater()
                return
            self.img_preview.setText("Image not found on CDN")
        reply.deleteLater()

    def closeEvent(self, event):
        self.extractor.cleanup()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    extractor = UnifiedExtractor()
    print("Extracting VROMF files (single pass)...")

    if not extractor.initialize():
        QMessageBox.critical(
            None,
            "Startup Error",
            "Could not locate War Thunder installation or wt_ext_cli.exe!",
        )
        sys.exit(1)

    window = VehicleExplorerApp(extractor)
    window.show()
    sys.exit(app.exec())
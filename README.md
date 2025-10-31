# 🏛️ Architecture Validator Pro

## Project Overview

**Architecture Validator Pro** is a cross-platform desktop application designed to automate the testing and verification of software architecture against compiled binaries and source code. It provides a user-friendly GUI to manage project configuration, perform symbol matching, analyze differences, and generate data outputs for further testing.

---

## ✨ Application Requirements

The application is built to fulfill the following ten core requirements:

1.  **GUI:** Must have a user-friendly graphical user interface (GUI) to ensure ease of use.
2.  **File Input:** Must be able to upload/read project files from specific paths, primarily handling **`.c`**, **`.h`**, and **`.elf`** files.
3.  **Symbol Matching:** Must search the **`.elf` file** for functions/parameters and match each input element with a symbol based on a **user-configurable confidence percentage**.
4.  **Data Presentation:** All core data must be presented to the user as a **simple, modifiable table**.
5.  **Table Customization:** The table must allow the user to **add/delete custom columns** and **delete/disable port lines** (rows).
6.  **Python List Generation:** Must be able to process the final table and generate structured **Python lists** containing parameters from each column.
7.  **Persistence:** Must have the ability to **save everything** (configuration and data) and load it later.
8.  **Difference Detection:** Must look for differences against a baseline upon user request and **color the differences**, allowing the user to approve or reject the changes.
9.  **Platform:** Must be able to run on **Windows**, with platform independence being a desirable bonus.
10. **Packaging:** Must be easily packaged into a simple distribution (all files in the same folder with a **`.bat` file for launching**).

---

## 🛠️ Technology Recommendations

The following stack is recommended to best meet the requirements, especially complex file parsing and GUI flexibility:

| Category | Recommended Technology | Rationale & Use |
| :--- | :--- | :--- |
| **Primary Language** | **Python** 🐍 | Excellent for scripting, file I/O, data manipulation, and easy packaging. Essential for generating Python lists (Req. 6). |
| **GUI Framework** | **PySide** (or PyQt) 🖼️ | Provides a robust, cross-platform GUI with superior **Table Widgets** (`QTableView`) perfect for complex data display, modification, and difference coloring (Req. 1, 4, 5, 8). |
| **ELF Parsing** | **`pyelftools`** | A dedicated Python library for extracting symbols, functions, and parameters from **`.elf` binaries** (Req. 3). |
| **Data Management** | **`pandas`** | Used internally for high-performance **DataFrame** management, simplifying table processing, difference comparison, and list generation (Req. 6, 8). |
| **Fuzzy Matching** | **`fuzzywuzzy`** | For implementing the core **confidence-based matching logic** (fuzzy search) required for symbol matching (Req. 3). |
| **Data Persistence** | **`json`** or **`pickle`** | Standard Python modules for serializing and deserializing the application's configuration and data (Req. 7). |
| **Deployment** | **`PyInstaller`** | Tool used to package the Python application into a standalone, single-folder distribution with an executable (Req. 10). |

---

## 🗺️ Chronological Development Roadmap (5 Phases)

The project is broken down into five distinct phases, moving from core functionality to final deployment.

### Phase 1: 🏗️ Core Backend Setup & File Parsing (Req. 2, 3, 7 - Logic)

| Step | Focus Area | Key Deliverable |
| :--- | :--- | :--- |
| **1.** Environment Setup | Install Python and all required libraries (`PySide/PyQt`, `pyelftools`, `pandas`, `fuzzywuzzy`). | A working Python virtual environment. |
| **2.** File I/O & Symbol Extraction | Implement the logic to read paths and use **`pyelftools`** to extract function/parameter symbols from a sample **`.elf` file**. | A script that successfully prints all symbols from a test `.elf` file. |
| **3.** Data Structure & Matching Logic | Define your core data structure (e.g., a **`pandas` DataFrame**) and implement the **confidence-based matching logic** using the extracted symbols. | A function that performs the symbol match and returns a confidence score. |
| **4.** Data I/O Proof-of-Concept | Implement simple functions to **save** and **load** the `pandas` DataFrame/configuration (Req. 7 - Logic). | Functions to save/load your configuration and data state. |

### Phase 2: 🖼️ Minimal GUI & Table Display (Req. 1, 4)

| Step | Focus Area | Key Deliverable |
| :--- | :--- | :--- |
| **5.** Basic Application Shell | Create the main window using **PySide/PyQt** and establish the tab structure for future expansion. | A simple window that launches. |
| **6.** Data Presentation | Integrate a **`QTableWidget`** or **`QTableView`** into the main window and populate it with the data from your `pandas` DataFrame (Req. 4). | A functional table displaying the core architecture data. |

### Phase 3: 🛠️ Table Manipulation & Feature Integration (Req. 5, 6, 7 - Integration)

| Step | Focus Area | Key Deliverable |
| :--- | :--- | :--- |
| **7.** Table Modification UI | Add GUI controls (buttons/menus) for the user to **add/delete custom columns** and **delete/disable port lines** (rows) (Req. 5). | A fully editable table interface. |
| **8.** Python List Generation | Implement the function to process the current table data and **generate the required Python lists** from each column's parameters (Req. 6). | A button that generates and confirms the required Python lists. |
| **9.** Save/Load Integration | Connect the save and load functions from Phase 1 to the GUI actions ("File -> Save," "File -> Load") (Req. 7 - Integration). | The ability to save the table state and reload it later. |

### Phase 4: 🔍 Difference Detection & Approval (Req. 8)

| Step | Focus Area | Key Deliverable |
| :--- | :--- | :--- |
| **10.** Difference Detection Logic | Implement the core comparison logic by comparing the *current* data against the *last saved/loaded* data. | Backend logic that identifies changed cells. |
| **11.** Visual Feedback & Approval | **Color-code the differences** in the table cells. Implement a mechanism (e.g., right-click menu or status column) allowing the user to **approve/reject** the changes (Req. 8). | Full implementation of difference detection, visualization, and user approval. |

### Phase 5: 📦 Deployment & Polish (Req. 9, 10)

| Step | Focus Area | Key Deliverable |
| :--- | :--- | :--- |
| **12.** Final Testing | Comprehensive testing on a **Windows** machine to ensure stability and compatibility (Req. 9). | A fully functional and stable application on the target OS. |
| **13.** Packaging | Use **`PyInstaller`** to create a single-folder distribution. | A single folder containing the executable and all dependencies. |
| **14.** Launch Script | Create the final **`.bat` launch file** in the same folder to execute the bundled program (Req. 10). | The final, portable application package ready for distribution. |

---

## 🎨 Concept Art: Tab-Based Design

The application will use a **tab-based design** to allow for future expansion, such as the "Task Design" features. The initial view is the "Architecture Validation" tab.
![](/Media/Concept Art.png "Concept Art")

### Architecture Validation Tab Layout

* **Top Panel:** File path inputs for ELF and Project files, alongside "Load" and "Save Configuration" buttons.
* **Central Area:** The core **Editable Data Table**, showing columns like `Port/Interface`, `Mapped Symbol`, `Type`, and custom columns. This table uses **color-coding** to highlight detected differences.
* **Bottom Control Panel:** Contains the **Matching Confidence Threshold slider**, controls for **Table Customization** (`Add Column`, `Disable Port`), and key action buttons like **"Run Validation & Compare"** and **"Generate Python Lists."**



---

## 📜 Licensing

This application is licensed under the MIT License.
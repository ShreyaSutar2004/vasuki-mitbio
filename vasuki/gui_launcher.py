
import os
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt5.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

from PyQt5 import QtWebEngine
QtWebEngine.QtWebEngine.initialize()

def launch(api_key=None):
    import os
    import sys

    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

    from PyQt5.QtCore import Qt, QCoreApplication
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    from PyQt5 import QtWebEngine
    QtWebEngine.QtWebEngine.initialize()

    from PyQt5.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)

    from .home import MainWindow

    window = MainWindow(api_key=api_key)
    window.show()
    app.processEvents()

    # QMessageBox.information(
    #     window,
    #     "Initializing AutoMod",
    #     "AutoMod is initializing scientific libraries.\n"
    #     "First run may take a few seconds."
    # )

    sys.exit(app.exec_())

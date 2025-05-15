import obspython as obs
import tkinter as tk
import ctypes
import threading

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
LWA_COLORKEY = 0x00000001
RED_DOT_PAUSE = 5
WS_EX_TOOLWINDOW = 0x80

OFF = False

B64_RECORD = "iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAYAAAA7MK6iAAAACXBIWXMAAAsTAAALEwEAmpwYAAAFTElEQVRIia2WXYxkRRXHf6fqdt/+mo+ebXZ2JsAqyOyuLAkMGpQsQUKMD0TfjDExxg0JL5r44gPxCZ6MD75h/OLFRE10HzZqxESNEBCWjQIPZAdGcSPi7KjLTu+O0933q+r4cLtn+nbfnriJlVR33apT538+/nWq5Ds/OMf8wgK1Wq322h8vfm1j49JjcRyfstYaEeFmmg7/ZTRWxTmn1Wp188SJk79+4GMPfitN091ut4v85Ge/wXt/6sc/+uFzF1995QOIUKs1MCK5ChnTWICQIooUp4fIqCpRNMB7x/0f+ej2F7549tO1sP5aUK1WG9//3rcvvPDC8wtrayep1erICHTUhvjoUN8E2KRtRWxFUeI45g8vvbiSptnLX/7KV2+1xz944qlf/vz8J++48y7q9QbWVrDWYozB2LxbY5Cx79GaNQa7L2P3943mclmLDOfa7SU2Lr0ZtJeW2ra9dOzZ7StX2p3O0SHoUFjMTXZBhJK50b9gxNDr7WGMWQ2iaLBSqzfyBZML3lybIsBUGwEjQrPZIoqixcAY66Zyuq+wkC2K2RyXL2O/TsmIyChlPhARL4Ds/5R5U6SPSwWX5JGxVcVWlHJqj3t9oMmI8Wa2tUVvxELSE3a3qvjM0OhkNI5kaAa7WxXSvkWsluyfMgGAoBCKicVcgSIW9rYr1BYc6196n2P39qktOgAG1y3/fKPB5q/a7G1XaK2kqBuPUnkRCmbM71ttLOxuV1g8nvDw17fpnBoQ37Ck/TzUrWMptz7Q4/hD/+HFb6xy4+9V5lZSvBvXMw1SoHAxQHnVGHQDmp2MR5/eYunOiJ2/hPTfD0j7hrRv6F8N2HknpLMW8chTV6gvOQZdC1JGwlLgkryokOwZTn9uh/YdMdffDZk6bSYnTvdvNY58KOKez18j6RnQspNSCjwtlPaFxeMJq+t9elcDxMwmjRildzVg5b4+C7en+6n4H4CnoZO+Zf72hPpSlntR1sZsSQeGcN7RWk5Jo8NvtkO1qRNsxWOsTmeirH4oGKOYQMFPFp9DgA9E8qMQ1Bz9qwHJnsVWSm0rjE2gpJEhvmGxVc9hx+mQRAjVlufaOzV2Loc0OinqZSZf1AuNTsaNd0N2LodUm77EwlLgaQEbgIsNb/9iEbFQnXN5cZggrHohnM8A2DjfxiWCCZgWLADPJKqiCq3llPcuNLn4zFFaR1PmVtL8SA33iVXmVhOatzguPrPMexeatJYzVA+/tQols9iGNdoozY7j0rklBjsBd3+2y8JtMTbMFbvY0P1ryJs/PcLl5+doLaeI5EaPHCjzOjgIcbmFqoINPa1jKZd/P8f2Gw2O3h3RWkkB2NsO+PelBoOuZW4lwdg89LMd0gmPx2+2SVEviIH51ZQsEv7xahOX5YI2UMIFx/xqgqqgvrCzXCEQqKoZYZZZNm517r3SuCWlcHhhIrRlno5WBVWVwHtncyJMws+qPOVcKP8+GKvqsHucc9ZUq+G/4miAKqh6FM//u+nwfY0q/d4eYRjumpMnP3w+SWKSJMI5h3ce7x2qDq8eVY8fdr2Jnu9xeO/wzuGcI81Sev0ea2snfms+/uCZp++9bz398+bbxHFMlmV5TzNclpFlKS4bjUt6WjZOp+SSJGZzc4PTp+/hE488+mSg6q6fffyJMyLmuddf/9ORaiWkVq8jyMHbr8CjsYefMLx3x7gx9qnD3MZRRBxHrK/fv3f28Sc+Y6zZku8+e452u40Y23nl5Zee3HzrrU/FSXybtdaIkVzxrOfTrDkAyfPqnNNqUN26a23td2ceevibiGzt7Fzjv0X5pGt3iiPfAAAAAElFTkSuQmCC"

B64_BUFFER = "iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAYAAAA7MK6iAAAACXBIWXMAAAsTAAALEwEAmpwYAAAEnklEQVRIieWXXWxURRSAv7l3t912W9qtlC7FkEqBEn9aUEMiJhgRRIIhJYUEItGAQUHUKARBo8ZEkASNGgwaE0EwCiYg8qAJETE2rU2QIAVewCI/bdndKpTtttvu9s69x4fdLf2D3RojD56XOzNn5nwz52fuvUpEuBVi3BLqrQS7Bg80njzTr6eSz75w3AkUAfXXpygYEi4FCP1Hp1VNGTBjpCfWQB1wb7KfBzwFVI3QzojAXmBeoql+BrKALkR2AY1ALbD83wRnA5uAi6A+RADDyFfZngvK47kL00xFYiaoncBR4P50RofEeJBUghwAyrFt1KgCzBL/98Tj9fa1q3/hOJ3mmJLFRq53qQ4FH5dIRxamOR04RiIEX/wTcAXIcURcoHBNmLjfuXrl2c5Pt7fHGuqwgwGwbQz/2GbPgzP359UszjPLJ32iL/yxDASU2q0gAurgcMbV4AskmdUGqAAiJShwl098o+enw5vaN6wlfubMOmCJAeUocITzAnuyJ01+/7Z3PyBn9tz1VlPT1kRBKEBKgeDUQVl9I/AWYCO2xjVpyq7YkR+WhxbOHw/Uuvz+sgEllGzrUOi8wMNjv/2u2TNrzg59rmkFpguQb4BF6cGnzhYgcg1Qhs8XdcLhvNDchwwr1NbuHjeuANvumytcr3RlurAut7a7/P7RY3+sF+X1djgd4VFJbenUqopgf87QrBaZB0ohgllcsr3z88/oDbVtc5eWDoCmHNm3zNa4SkuLekOhbZ27d2CWlOxMeEUBLByMGa6cZgAojwcdDHwZb6jDgFUp1970lSKCAatj9bXYbW27yfYkV8j0TMAVIKhcL3bzxdNWS3Op4fWaKbAaZsEAcK7H1K0tPvtya6ORk5PSlGUC9iY0BmJp0LoAcwQXnGGC4+SIYycSL7HVIQaGsaiuAEgshllcPNosKjpHT0/GXInFMQsLg0ahzy+9vanh5gzAcgpAerpx3VH+qPueKsu29AlMMz3VNLG1PuGunCausgnV0tNNMisaMwBzGBTYDth6rXfxUoBVTmcnGDdxuWHghMMYsDJvyRMQj63BcVLag+nBStWBtKJAt7Tc552/YF7hCy/9akUir0l39/Bww0C6urCi0Q0F6145nvPInBp9ufXuRIypA86lBwuAWg0KHBs7FDzge2vzeN/KVVt0OLzICgSapKcb0RqxLCTahRUInNWRSHXRiy9v9b359mQdCOzrO61SzyU3MPB8N7gyAfaDqkFrDJ+v3Sges6B7395fIrt2YJ0+OcWJdj2gTFfUyM8/5q6adiH/yRV4q2vm6rbQAYl05GK6QLEeeA9gamVFxmCAI8AsbAey3LjGl30l0a6P4yd+a7Cv/IlyZ2EWjyG7smo22Z41+tLFamydCsdmlHo9ZWhkYAWI+gjkeQAcQWVlYRQWHlWenKfFsQ9JLHa709EB2krWLZeAjcDX/V08QnDfW+gxUK8CMxOKRCKg1FKEPcl+LbAX2AlYfetvAE73BZKSQyCHQM0AlgETAXcSVAa8AzwD/J6hvYzBKWkAaQAQMFXCG1uAYmB0Apz4tE0nQ1z9X8n/7xfmb0gn8Knb3EhiAAAAAElFTkSuQmCC"


STATUS = {"record": False, "buffer": False}
CORNER = "top-left"
MARGIN = 5
SIZE = (30, 30)
UPDATE_MS = 100
overlay = None


def set_clickthrough(hwnd):
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    styles |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, styles)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_COLORKEY)


def _hide_buffer():
    STATUS["buffer"] = False


class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.config(bg="#000000")
        self.root.attributes("-alpha", 1)
        self.root.wm_attributes("-topmost", 1)
        self.root.attributes("-transparentcolor", "#000000")
        set_clickthrough(self.root.winfo_id())
        self.record_img = tk.PhotoImage(data=B64_RECORD)
        self.buffer_img = tk.PhotoImage(data=B64_BUFFER)
        self.label = tk.Label(self.root, bg="black", bd=0)
        self.label.pack()
        self._loop()

    def _update_position(self):
        global OFF
        w, h = SIZE
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if CORNER == "off":
            OFF = True
            return
        elif CORNER == "top-left":
            x, y = MARGIN, MARGIN
        elif CORNER == "top-right":
            x, y = sw - w - MARGIN, MARGIN
        elif CORNER == "bottom-left":
            x, y = MARGIN, sh - h - MARGIN
        else:
            x, y = sw - w - MARGIN, sh - h - MARGIN
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _loop(self):
        if OFF:
            self.label.config(image="")
            self.root.after(UPDATE_MS, self._loop)
            return
        self._update_position()
        if STATUS["buffer"]:
            self.label.config(image=self.buffer_img)
            self.root.after(RED_DOT_PAUSE * 1000, _hide_buffer)
        elif STATUS["record"]:
            self.label.config(image=self.record_img)
        else:
            self.label.config(image="")
        self.root.after(UPDATE_MS, self._loop)


def event_handler(evt):
    if evt == obs.OBS_FRONTEND_EVENT_RECORDING_STARTING:
        STATUS["record"] = True
    elif evt == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED:
        STATUS["record"] = False
    elif evt == obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED:
        STATUS["buffer"] = True


def start_app():
    global overlay
    overlay = Overlay()
    overlay.root.mainloop()


def script_description():
    return "Индикатор записи и буфера мгновенного повтора с выбором угла экрана. © Tap1x, 2025 — До конца времен."

def script_properties():
    props = obs.obs_properties_create()
    corners = obs.obs_properties_add_list(
        props,
        "corner",
        "Угол экрана",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING
    )
    for key, label in [
        ("top-left", "Верхний левый"),
        ("top-right", "Верхний правый"),
        ("bottom-left", "Нижний левый"),
        ("bottom-right", "Нижний правый"),
        ("off", "Выключено"),
    ]:
        obs.obs_property_list_add_string(corners, label, key)

    return props


def script_update(settings):
    global CORNER, OFF
    c = obs.obs_data_get_string(settings, "corner")
    if c in ("top-left", "top-right", "bottom-left", "bottom-right", "off"):
        CORNER = c
        if c == "off":
            OFF = True
        else:
            OFF = False


obs.obs_frontend_add_event_callback(event_handler)
threading.Thread(target=start_app, daemon=True).start()

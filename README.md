# SMAA widget

This widget applies a Subpixel Morphological Antialiasing (SMAA) to all the
children. It's a 3-pass shader and works currently only on Desktop. You need at
minimum OpenGL 4.3 or 4.4 drivers. It also require at least Kivy 1.8.1 from git.

It has been tested only on Linux with NVIDIA card (GTX 560, 310.44 drivers)

Read more about SMAA:

- Official Website: http://www.iryoku.com/smaa/
- Source code: https://github.com/iryoku/smaa

# Usage

The widget is intended to be used with vector graphics. Don't use it with text
or images in it, cause if you have already anti-aliasing on the font or image,
it will add more AA, which result to bad AA. Ie for a text, it will shrink more
the font's weight.

You need to pass the size of the SMAA widget from the start. It doesn't support
any resizing at the moment.

![Comparaison](/screenshot.png)

Example:

```python
from kivy.garden.smaa import SMAA
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.graphics import Color, Triangle

class SMAAApp(App):

	def build(self):
		smaa = SMAA(size=Window.size)

		wid = Widget()
		w, h = Window.size
		with wid.canvas:
			Color(1, 1, 1)
			Triangle(points=(
				w / 2 - w * .25, h / 2 - h * .25,
				w / 2, h / 2 + h * .25,
				w / 2 + w * .25, h / 2 - h * .25))
		smaa.add_widget(wid)

		return smaa

SMAAApp().run()
```

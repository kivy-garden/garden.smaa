'''
Subpixel Morphological Antialiasing widget
==========================================

'''

import kivy
kivy.require('1.8.1')

from os.path import dirname, join
from kivy.uix.widget import Widget
from kivy.graphics import Rectangle, BindTexture, RenderContext, Color, \
        Canvas, Callback
from kivy.graphics.fbo import Fbo
from kivy.graphics.texture import Texture
from kivy.graphics.gl_instructions import ClearColor, ClearBuffers
from kivy.graphics.opengl import glEnable, glDisable, GL_BLEND
from kivy.properties import OptionProperty


SEARCHTEX_WIDTH = 66
SEARCHTEX_HEIGHT = 33
AREATEX_WIDTH = 160
AREATEX_HEIGHT = 560


class SMAA(Widget):

    debug = OptionProperty('', options=('', 'edges', 'blend', 'source'))
    '''Texture to show instead of the result:

    - `edges` will show you the result of the edges detection shader
    - `blend` will show you the result of the blending shader
    - `source` will show you the initial drawing of children, before any pass.
    '''

    quality = OptionProperty('ultra', options=(
        'low', 'medium', 'high', 'ultra'))
    '''Quality of the shader. The more you ask, the slower it will be.
    '''

    def __init__(self, **kwargs):
        self._g_debug = []
        self._g_debug_added = False
        if 'size' not in kwargs:
            from kivy.core.window import Window
            kwargs['size'] = Window.size
        self.size = kwargs['size']
        self.init_smaa()
        super(SMAA, self).__init__()
        self.canvas.add(self.smaa_canvas)
        self.canvas.ask_update()

    def add_widget(self, *args):
        canvas = self.smaa_canvas
        self.canvas = self.albedo_fbo
        super(SMAA, self).add_widget(*args)
        self.canvas = canvas

    def remove_widget(self, *args):
        canvas = self.smaa_canvas
        self.canvas = self.albedo_fbo
        super(SMAA, self).remove_widget(*args)
        self.canvas = canvas

    def init_smaa(self):
        curdir = dirname(__file__)

        # load shaders sources
        with open(join(curdir, 'SMAA.h'), 'r') as fd:
            smaa_h = fd.read()

        config = '''
            #version 410 compatibility
            #define SMAA_PIXEL_SIZE vec2(1.0 / {width}, 1.0 / {height})
            #define SMAA_PRESET_{quality} 1
            #define SMAA_GLSL_4 1
        '''.format(
                width=self.width,
                height=self.height,
                quality=self.quality.upper())

        header_vs = config + '''
            #define SMAA_ONLY_COMPILE_VS 1

            in vec2 vPosition;
            in vec2 vTexCoords0;
            uniform mat4 modelview_mat;
            uniform mat4 projection_mat;
        ''' + smaa_h

        header_fs = config + '''
            #define SMAA_ONLY_COMPILE_PS 1
        ''' + smaa_h

        edge_vs = header_vs + '''
            out vec2 texcoord;
            out vec4 offset[3];
            out vec4 dummy2;
            void main()
            {
                texcoord = vTexCoords0;
                vec4 dummy1 = vec4(0);
                SMAAEdgeDetectionVS(dummy1, dummy2, texcoord, offset);
                gl_Position = projection_mat * modelview_mat * vec4(vPosition.xy, 0.0, 1.0);
            }
        '''

        edge_fs = header_fs + '''
            uniform sampler2D albedo_tex;
            in vec2 texcoord;
            in vec4 offset[3];
            in vec4 dummy2;
            void main()
            {
                #if SMAA_PREDICATION == 1
                    gl_FragColor = SMAAColorEdgeDetectionPS(texcoord, offset, albedo_tex, depthTex);
                #else
                    gl_FragColor = SMAAColorEdgeDetectionPS(texcoord, offset, albedo_tex);
                #endif
            }
        '''

        blend_vs = header_vs + '''
            out vec2 texcoord;
            out vec2 pixcoord;
            out vec4 offset[3];
            out vec4 dummy2;
            void main()
            {
                texcoord = vTexCoords0;
                vec4 dummy1 = vec4(0);
                SMAABlendingWeightCalculationVS(dummy1, dummy2, texcoord, pixcoord, offset);
                gl_Position = projection_mat * modelview_mat * vec4(vPosition.xy, 0.0, 1.0);
            }
        '''

        blend_fs = header_fs + '''
            uniform sampler2D edge_tex;
            uniform sampler2D area_tex;
            uniform sampler2D search_tex;
            in vec2 texcoord;
            in vec2 pixcoord;
            in vec4 offset[3];
            in vec4 dummy2;
            void main()
            {
                gl_FragColor = SMAABlendingWeightCalculationPS(texcoord, pixcoord, offset, edge_tex, area_tex, search_tex, ivec4(0));
            }
        '''

        neighborhood_vs = header_vs + '''
            out vec2 texcoord;
            out vec4 offset[2];
            out vec4 dummy2;
            void main()
            {
                texcoord = vTexCoords0;
                vec4 dummy1 = vec4(0);
                SMAANeighborhoodBlendingVS(dummy1, dummy2, texcoord, offset);
                gl_Position = projection_mat * modelview_mat * vec4(vPosition.xy, 0.0, 1.0);
            }
        '''

        neighborhood_fs = header_fs + '''
            uniform sampler2D albedo_tex;
            uniform sampler2D blend_tex;
            in vec2 texcoord;
            in vec4 offset[2];
            in vec4 dummy2;
            void main()
            {
                gl_FragColor = SMAANeighborhoodBlendingPS(texcoord, offset, albedo_tex, blend_tex);
            }
        '''

        size = self.size
        self.albedo_tex = Texture.create(size=size, bufferfmt='float')
        self.albedo_fbo = Fbo(size=size, texture=self.albedo_tex)

        self.edge_tex = Texture.create(size=size, bufferfmt='float')
        self.edge_fbo = Fbo(size=size, vs=edge_vs, fs=edge_fs,
                texture=self.edge_tex)
        self.edge_fbo.bind()
        self.edge_fbo['albedo_tex'] = 0
        self.edge_fbo.release()

        self.blend_tex = Texture.create(size=size, bufferfmt='float')
        self.blend_fbo = Fbo(size=size, vs=blend_vs, fs=blend_fs,
                texture=self.blend_tex)
        self.blend_fbo.bind()
        self.blend_fbo['edge_tex'] = 0
        self.blend_fbo['area_tex'] = 1
        self.blend_fbo['search_tex'] = 2
        self.blend_fbo.release()

        self.neighborhood = RenderContext(
                use_parent_modelview=True,
                use_parent_projection=True,
                vs=neighborhood_vs, fs=neighborhood_fs)
        with self.neighborhood:
            self.neighborhood['albedo_tex'] = 0
            self.neighborhood['blend_tex'] = 1

        self.area_tex = Texture.create(
                size=(AREATEX_WIDTH, AREATEX_HEIGHT),
                colorfmt='rg', icolorfmt='rg8')

        with open(join(curdir, 'smaa_area.raw'), 'rb') as fd:
            self.area_tex.blit_buffer(
                    fd.read(), colorfmt='rg')

        self.search_tex = Texture.create(
                size=(SEARCHTEX_WIDTH, SEARCHTEX_HEIGHT),
                colorfmt='red', icolorfmt='r8')

        self.search_tex.min_filter = 'nearest'
        self.search_tex.mag_filter = 'nearest'

        with open(join(curdir, 'smaa_search.raw'), 'rb') as fd:
            self.search_tex.blit_buffer(
                    fd.read(), colorfmt='red')

        with self.albedo_fbo:
            ClearColor(0, 0, 0, 0)
            ClearBuffers()

        with self.edge_fbo:
            Rectangle(size=self.size, texture=self.albedo_tex)

        with self.blend_fbo:
            BindTexture(index=1, texture=self.area_tex)
            BindTexture(index=2, texture=self.search_tex)
            Rectangle(size=self.size, texture=self.edge_tex)

        self.neighborhood.add(self.albedo_fbo)
        self.neighborhood.add(Callback(lambda *x: glDisable(GL_BLEND)))
        self.neighborhood.add(self.edge_fbo)
        self.neighborhood.add(self.blend_fbo)
        self.neighborhood.add(Callback(lambda *x: glEnable(GL_BLEND)))
        with self.neighborhood:
            BindTexture(index=1, texture=self.blend_tex)
            Rectangle(size=self.size, texture=self.albedo_tex)

        self.smaa_canvas = Canvas()
        with self.smaa_canvas.before:
            def do_stuff(*args):
                self.albedo_fbo.bind()
                self.albedo_fbo.clear_buffer()
                self.albedo_fbo.release()
                self.edge_fbo.bind()
                self.edge_fbo.clear_buffer()
                self.edge_fbo.release()
                self.blend_fbo.bind()
                self.blend_fbo.clear_buffer()
                self.blend_fbo.release()
                self.albedo_fbo.ask_update()
                self.edge_fbo.ask_update()
                self.blend_fbo.ask_update()
                self.neighborhood.ask_update()
            Callback(do_stuff)
        self.smaa_canvas.add(self.neighborhood)

        self._g_debug_added = False
        self._g_debug = [
            Callback(lambda *x: glDisable(GL_BLEND)),
            Color(0, 0, 0, 1),
            Rectangle(size=self.size),
            Color(1, 1, 1, 1),
            Rectangle(size=self.size),
            Callback(lambda *x: glEnable(GL_BLEND))]

    def on_debug(self, instance, value):
        g_debug = self._g_debug
        if self._g_debug_added:
            for instr in g_debug:
                self.canvas.after.remove(instr)
        if value == '':
            return
        elif value == 'edges':
            g_debug[-2].texture = self.edge_tex
        elif value == 'blend':
            g_debug[-2].texture = self.blend_tex
        elif value == 'source':
            g_debug[-2].texture = self.albedo_tex
        self._g_debug_added = True
        for instr in g_debug:
            self.canvas.after.add(instr)

    def on_quality(self, instance, value):
        self.reload_smaa()

    def reload_smaa(self):
        debug = self.debug
        self.debug = ''
        children = self.children[:]
        for child in children:
            self.remove_widget(child)
        self.canvas.remove(self.smaa_canvas)
        self.init_smaa()
        self.canvas.add(self.smaa_canvas)
        for child in children:
            self.add_widget(child)
        self.debug = debug


if __name__ == '__main__':

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

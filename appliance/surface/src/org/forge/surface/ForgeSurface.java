package org.forge.surface;

import android.graphics.PixelFormat;
import android.view.Surface;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

/** app_process entry point for the Forge native panel SurfaceControl host. */
public final class ForgeSurface {
    private static final int WIDTH = 800;
    private static final int HEIGHT = 1280;

    private ForgeSurface() { }

    private static native int run(Surface surface, String musicSocket, String webSurface,
            String x11Socket, boolean homeDashboard);

    public static void main(String[] args) {
        if (args.length != 5 || !absolute(args[0]) || !absolute(args[1])
                || !absolute(args[2]) || !absolute(args[3])
                || !("0".equals(args[4]) || "1".equals(args[4]))) {
            throw new IllegalArgumentException("usage: ForgeSurface <install> <music socket> "
                    + "<xwd path> <x11 socket> <home flag 0|1>");
        }

        System.load(args[0] + "/libforge-panel.so");
        SurfaceHost host = SurfaceHost.create();
        int status;
        try {
            status = run(host.surface, args[1], args[2], args[3], "1".equals(args[4]));
        } finally {
            host.close();
        }
        if (status != 0) {
            System.exit(status);
        }
    }

    private static boolean absolute(String value) {
        return value != null && value.startsWith("/");
    }

    private static final class SurfaceHost {
        final Surface surface;
        final Object control;
        final Class<?> controlClass;

        private SurfaceHost(Surface surface, Object control, Class<?> controlClass) {
            this.surface = surface;
            this.control = control;
            this.controlClass = controlClass;
        }

        static SurfaceHost create() {
            Surface surface = null;
            Object control = null;
            Class<?> controlClass = null;
            try {
                surface = (Surface) constructor(Surface.class).newInstance();
                controlClass = Class.forName("android.view.SurfaceControl");
                Class<?> builderClass = Class.forName("android.view.SurfaceControl$Builder");
                Object builder = constructor(builderClass).newInstance();
                invoke(builderClass, builder, "setName", new Class<?>[] {String.class},
                        "ForgeOS Panel");
                invoke(builderClass, builder, "setBufferSize", new Class<?>[] {int.class, int.class},
                        WIDTH, HEIGHT);
                invoke(builderClass, builder, "setFormat", new Class<?>[] {int.class},
                        PixelFormat.RGBA_8888);
                invoke(builderClass, builder, "setOpaque", new Class<?>[] {boolean.class}, true);
                invoke(builderClass, builder, "setSecure", new Class<?>[] {boolean.class}, true);
                control = invoke(builderClass, builder, "build", new Class<?>[0]);

                Method copyFrom = method(Surface.class, "copyFrom", controlClass);
                copyFrom.invoke(surface, control);

                Class<?> transactionClass = Class.forName("android.view.SurfaceControl$Transaction");
                Object transaction = constructor(transactionClass).newInstance();
                try {
                    invoke(transactionClass, transaction, "setLayer",
                            new Class<?>[] {controlClass, int.class}, control, Integer.MAX_VALUE);
                    invoke(transactionClass, transaction, "show", new Class<?>[] {controlClass}, control);
                    invoke(transactionClass, transaction, "apply", new Class<?>[0]);
                } finally {
                    release(transaction);
                }
                return new SurfaceHost(surface, control, controlClass);
            } catch (ReflectiveOperationException | RuntimeException error) {
                if (surface != null) {
                    surface.release();
                }
                release(control);
                throw new IllegalStateException("Android 10 SurfaceControl API is unavailable", error);
            }
        }

        void close() {
            try {
                Class<?> transactionClass = Class.forName("android.view.SurfaceControl$Transaction");
                Object transaction = constructor(transactionClass).newInstance();
                try {
                    invoke(transactionClass, transaction, "remove", new Class<?>[] {controlClass}, control);
                    invoke(transactionClass, transaction, "apply", new Class<?>[0]);
                } finally {
                    release(transaction);
                }
            } catch (ReflectiveOperationException | RuntimeException ignored) {
                // Resource release below is still required if the removal transaction cannot run.
            } finally {
                surface.release();
                release(control);
            }
        }

        private static Constructor<?> constructor(Class<?> type) throws NoSuchMethodException {
            Constructor<?> constructor = type.getDeclaredConstructor();
            constructor.setAccessible(true);
            return constructor;
        }

        private static Method method(Class<?> type, String name, Class<?>... parameterTypes)
                throws NoSuchMethodException {
            Method method = type.getDeclaredMethod(name, parameterTypes);
            method.setAccessible(true);
            return method;
        }

        private static Object invoke(Class<?> type, Object receiver, String name,
                Class<?>[] parameterTypes, Object... arguments) throws ReflectiveOperationException {
            return method(type, name, parameterTypes).invoke(receiver, arguments);
        }

        private static void release(Object resource) {
            if (resource == null) {
                return;
            }
            try {
                method(resource.getClass(), "release").invoke(resource);
            } catch (ReflectiveOperationException | RuntimeException ignored) {
                try {
                    method(resource.getClass(), "close").invoke(resource);
                } catch (ReflectiveOperationException | RuntimeException ignoredAgain) {
                    // The platform object has no accessible release method.
                }
            }
        }
    }
}

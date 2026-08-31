CC ?= cc
OUTPUT ?= satellite1-ws281x-render

CPPFLAGS += -I../third_party/rpi_ws281x
CFLAGS += -O2 -D_FORTIFY_SOURCE=2 -fstack-protector-strong -fPIE -Wall -Wextra -Werror
LDFLAGS += -pie -Wl,-z,relro,-z,now

SOURCES = \
	satellite1-ws281x-render.c \
	../third_party/rpi_ws281x/dma.c \
	../third_party/rpi_ws281x/mailbox.c \
	../third_party/rpi_ws281x/pcm.c \
	../third_party/rpi_ws281x/pwm.c \
	../third_party/rpi_ws281x/rpihw.c \
	../third_party/rpi_ws281x/ws2811.c

$(OUTPUT): $(SOURCES)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $(SOURCES) -lm

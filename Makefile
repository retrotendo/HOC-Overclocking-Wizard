#-------------------------------------------------------------------------------
.SUFFIXES:
#-------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITPRO)),)
$(error "Please set DEVKITPRO in your environment. export DEVKITPRO=<path to>/devkitpro")
endif

TOPDIR ?= $(CURDIR)
include $(DEVKITPRO)/libnx/switch_rules

TARGET      := HOC-Undervolting-Wizard
BUILD       := build
SOURCES     := source
DATA        := data
INCLUDES    := include
ROMFS       := romfs

APP_TITLE   := HOC Undervolting Wizard
APP_AUTHOR  := Retrotendo / Community
APP_VERSION := 0.4.0-beta.52

ARCH        := -march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE
CFLAGS      := -g -Wall -O2 -ffunction-sections $(ARCH) $(DEFINES) `curl-config --cflags`
CFLAGS      += $(INCLUDE) -D__SWITCH__ -DHOC_WIZARD_VERSION=\"$(APP_VERSION)\"
CFLAGS      += -I$(PORTLIBS)/include/freetype2
CXXFLAGS    := $(CFLAGS) -fno-rtti -fno-exceptions -std=gnu++17
ASFLAGS     := -g $(ARCH)
LDFLAGS     = -specs=$(DEVKITPRO)/libnx/switch.specs -g $(ARCH) -Wl,-Map,$(notdir $*.map)

PKGCONF     := $(PORTLIBS)/bin/aarch64-none-elf-pkg-config
FREETYPE_LIBS := $(shell $(PKGCONF) --static --libs freetype2 2>/dev/null)
ifeq ($(strip $(FREETYPE_LIBS)),)
FREETYPE_LIBS := -lfreetype -lbz2 -lpng16 -lz -lharfbuzz -pthread -lm
endif
LIBS        := -ldeko3dd `curl-config --libs` $(FREETYPE_LIBS)
LIBDIRS     := $(PORTLIBS) $(LIBNX)

ifneq ($(BUILD),$(notdir $(CURDIR)))
export OUTPUT := $(CURDIR)/$(TARGET)
export TOPDIR := $(CURDIR)
export VPATH  := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
                 $(foreach dir,$(DATA),$(CURDIR)/$(dir))
export DEPSDIR := $(CURDIR)/$(BUILD)

ifneq ($(strip $(APP_TITLE)),)
export NROFLAGS += --nacp=$(CURDIR)/$(TARGET).nacp
endif
export NROFLAGS += --romfsdir=$(CURDIR)/$(ROMFS)

CFILES   := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
SFILES   := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
BINFILES := $(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))

export LD := $(CXX)
export OFILES_BIN := $(addsuffix .o,$(BINFILES))
export OFILES_SRC := $(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)
export OFILES := $(OFILES_BIN) $(OFILES_SRC)
export HFILES_BIN := $(addsuffix .h,$(subst .,_,$(BINFILES)))
export INCLUDE := $(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) \
                 $(foreach dir,$(LIBDIRS),-I$(dir)/include) \
                 -I$(CURDIR)/$(BUILD)
export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib)

ROMFS_SHADERS := $(ROMFS)/shaders
GPU_SHADER := $(ROMFS_SHADERS)/gpu_stress.dksh

.PHONY: all clean $(BUILD)
all: $(GPU_SHADER) $(BUILD)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

$(BUILD):
	@mkdir -p $@

$(ROMFS_SHADERS):
	@mkdir -p $@

$(GPU_SHADER): source/gpu_stress.glsl | $(ROMFS_SHADERS)
	@echo "{comp} gpu_stress.glsl"
	@uam -s comp -o $@ $<

clean:
	@echo clean ...
	@rm -fr $(BUILD) $(ROMFS) $(TARGET).nro $(TARGET).nacp $(TARGET).elf
else
DEPENDS := $(OFILES:.o=.d)
ifneq ($(strip $(APP_TITLE)),)
$(OUTPUT).nro : $(OUTPUT).elf $(OUTPUT).nacp
else
$(OUTPUT).nro : $(OUTPUT).elf
endif
$(OUTPUT).elf : $(OFILES)

%.nacp:
	@nacptool --create "$(APP_TITLE)" "$(APP_AUTHOR)" "$(APP_VERSION)" $@
-include $(DEPENDS)
endif

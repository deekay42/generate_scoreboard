REM this script needs to be given the path to the pythondir. there it'll create a folder named dist with all required dlls and libs
REM it will also create cython.h in the include dir in the pythondir
if [%1]==[] goto usage
if [%2]==[] goto usage

set PYTHONPATH=C:\Program Files\Python37\python37.zip;C:\Program Files\Python37\DLLs;C:\Program Files\Python37\lib;C:\Program Files\Python37;C:\Users\Dom\AppData\Roaming\Python\Python37\site-packages;C:\Program Files\Python37\lib\site-packages
set PYTHONHOME=C:\Program Files\Python37
set PATH=C:\Program Files (x86)\Windows Kits\10\Redist\10.0.17763.0\ucrt\DLLs\x64;%PATH%;%PYTHONPATH%
call vcvars64.bat
set INIT_DIR=%cd%
CALL :NORMALIZEPATH %~1 
set PYTHONDIR=%RETVAL%
CALL :NORMALIZEPATH %~2
set OUT_DIR=%RETVAL%
echo %PYTHONDIR%
echo %OUT_DIR%
rmdir /s /q %OUT_DIR%
mkdir %OUT_DIR%
REM rmdir /s /q .\dist
cd %PYTHONDIR%
rmdir /s /q .\tmp_build
mkdir tmp_build
set TCL_LIBRARY=C:\Program Files\Python37\tcl\tcl8.6
set TK_LIBRARY=C:\Program Files\Python37\tcl\tk8.6
set TFL_LIBRARY=C:\Program Files\Python37\Lib\site-packages\tflearn
set PKG_LIBRARY=C:\Program Files\Python37\Lib\site-packages\pkg_resources

python -m PyInstaller -d noarchive main.py --distpath tmp_build --add-data "%TCL_LIBRARY%;tcl" --add-data "%TK_LIBRARY%;tk" --add-data "%TFL_LIBRARY%;tflearn" --add-data "%PKG_LIBRARY%;pkg_resources" --exclude-module tensorflow_core --exclude-module tensorflow --path "C:\Program Files\Python37\Library"
MOVE tmp_build\main\*.dll tmp_build
del /Q /S .\tmp_build\main\*.exe
rmdir /s /q .\tmp_build\main\utils
rmdir /s /q .\tmp_build\main\train_model
rmdir /s /q .\tmp_build\main\constants

mkdir tmp_build\tmp
python "build/setup.py" build_ext --build-lib tmp_build\tmp
del /Q /S .\tmp_build\tmp\*.c
del /Q /S .\tmp_build\tmp\*.pyc
ROBOCOPY /NFL /NDL  tmp_build\tmp tmp_build\main *.* /S /MOVE
MOVE tmp_build\main tmp_build\py_libs
echo #cython: language_level=3 >cython_main.pyx
echo import os; os.environ["TCL_LIBRARY"]="py_libs\\tcl"; os.environ["TK_LIBRARY"]="py_libs\\tk"; import sys; sys.path = ["py_libs/base_library.zip", "py_libs"]; sys.argv = ["cython_main.pyx"]; import main; main.debug = False; m = main.Main(); m.run()>>cython_main.pyx
cython cython_main.pyx --embed
del /Q cython_main.pyx

sed -i "s#int wmain.*#int runCythonCode(){  int argc = 0;  wchar_t** argv = nullptr; Py_SetPath(L\"py_libs;py_libs/base_library.zip\");#" cython_main.c
move cython_main.c "%INIT_DIR%\include\cython.h"
SET src_folder=tmp_build
SET tar_folder=%OUT_DIR%
ROBOCOPY /NFL /NDL %src_folder% %tar_folder% *.* /S /MOVE
cd %INIT_DIR%


COPY %INIT_DIR%\windows\google-services.json %OUT_DIR%
mkdir %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\champ2id.json %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\item2id.json %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\self2id.json %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\kda2id.json %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\my_champ_embs_normed.npy %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\opp_champ_embs_normed.npy %OUT_DIR%\assets\data
COPY %PYTHONDIR%\..\assets\data\champ_vs_roles.json %OUT_DIR%\assets\data
COPY %PYTHONDIR%\tensorflow.dll %OUT_DIR%
COPY %PYTHONDIR%\cpredict.dll %OUT_DIR%
ECHO F | XCOPY %PYTHONDIR%\models\best\imgs\items\model.pb %OUT_DIR%\models\best\imgs\items\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\imgs\champs\model.pb %OUT_DIR%\models\best\imgs\champs\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\imgs\kda\model.pb %OUT_DIR%\models\best\imgs\kda\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\imgs\self\model.pb %OUT_DIR%\models\best\imgs\self\model.pb

ECHO F | XCOPY %PYTHONDIR%\models\best\next_items\boots\model.pb %OUT_DIR%\models\best\next_items\boots\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\next_items\standard\model.pb %OUT_DIR%\models\best\next_items\standard\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\next_items\late\model.pb %OUT_DIR%\models\best\next_items\late\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\next_items\first_item\model.pb %OUT_DIR%\models\best\next_items\first_item\model.pb
ECHO F | XCOPY %PYTHONDIR%\models\best\next_items\starter\model.pb %OUT_DIR%\models\best\next_items\starter\model.pb

ECHO F | XCOPY %PYTHONDIR%\..\assets\icons\logo_head_only.png %OUT_DIR%\assets\icons\logo_head_only.png
ECHO F | XCOPY %PYTHONDIR%\..\assets\icons\logo_head_small.png %OUT_DIR%\assets\icons\logo_head_small.png
ECHO F | XCOPY %PYTHONDIR%\..\assets\icons\logo.png %OUT_DIR%\assets\icons\logo.png


REM mkdir %OUT_DIR%\assets\tesseract
REM COPY %PYTHONDIR%\..\assets\tesseract\sep.png %OUT_DIR%\assets\tesseract

ROBOCOPY /NFL /NDL  %PYTHONDIR%\tessdata %OUT_DIR%\tessdata *.* /S
ROBOCOPY /NFL /NDL  %PYTHONDIR%\..\assets\fonts %OUT_DIR%\assets\fonts *.* /S
REM ROBOCOPY /NFL /NDL  %PYTHONDIR%\..\assets\icons %OUT_DIR%\assets\icons *.* /S
ROBOCOPY /NFL /NDL  %PYTHONDIR%\..\assets\imgs %OUT_DIR%\assets\imgs *.* /S
ROBOCOPY /NFL /NDL  %PYTHONDIR%\..\assets\item_imgs %OUT_DIR%\assets\item_imgs *.* /S
ROBOCOPY /NFL /NDL  %PYTHONDIR%\..\assets\train_imgs\kda %OUT_DIR%\assets\train_imgs\kda *.* /S

exit /B

:usage
@echo Usage: Need to specify 1:pythondir 2:out_dir
exit /B 1

:NORMALIZEPATH
  SET RETVAL=%~dpfn1
  EXIT /B
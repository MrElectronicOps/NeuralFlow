# Desktop dependency notice sources

These notices accompany the actual self-contained .NET 10.0.11 desktop and
capture applications. Upstream license files are preserved byte for byte.
The other bundled Python and image-library notices remain with their packages,
as described in the root `THIRD-PARTY-NOTICES.md`.

## Installed official NuGet packages

Copied from the packages used by this build, rather than a different runtime
version. Package references below are relative to the standard NuGet package
cache; no machine-specific user paths are included.

| Included file | Exact package source |
| --- | --- |
| dotnet-runtime-10.0.11-LICENSE.txt | Microsoft.NETCore.App.Runtime.win-x64 10.0.11 / LICENSE.TXT |
| dotnet-runtime-10.0.11-THIRD-PARTY-NOTICES.txt | Microsoft.NETCore.App.Runtime.win-x64 10.0.11 / THIRD-PARTY-NOTICES.TXT |
| dotnet-desktop-10.0.11-LICENSE.txt | Microsoft.WindowsDesktop.App.Runtime.win-x64 10.0.11 / LICENSE |
| cswinrt-2.2.0-LICENSE.txt | Microsoft.Windows.CsWinRT 2.2.0 / LICENSE |
| cswinrt-2.2.0-NOTICE.txt | Microsoft.Windows.CsWinRT 2.2.0 / NOTICE.txt |
| sharpgen.runtime-2.4.2-beta.nuspec | SharpGen.Runtime 2.4.2-beta / sharpgen.runtime.nuspec |
| sharpgen.runtime.com-2.4.2-beta.nuspec | SharpGen.Runtime.COM 2.4.2-beta / sharpgen.runtime.com.nuspec |

The capture package `Microsoft.Windows.SDK.NET.Ref` 10.0.22621.57 supplies
Microsoft.Windows.SDK.NET.dll and WinRT.Runtime.dll. The shipped WinRT runtime
reports 2.2.0.48161 and upstream commit
`8649ee3eeb2445ca2a36d80d878ef60b96a6c65d`, matching the C#/WinRT 2.2.0 source.
The SDK package's license URL is https://aka.ms/WinSDKLicenseURL . Its resolved
Microsoft download is preserved as `windows-sdk-LICENSE.rtf`:
https://download.microsoft.com/download/0/F/F/0FF2B061-47DD-4F55-89B6-FD1D8C44F14D/sdk_license.rtf .

## Exact upstream source files

The Vortice and SharpGen repository commits are the commits recorded in the
installed packages' NuGet manifests. Their manifests declare MIT and provide
the applicable copyright holder names. SharpGen's manifests retain its newer
copyright years and contributor attribution in addition to the repository
license text.

| Included file | Pinned upstream source |
| --- | --- |
| vortice-windows-3.8.1-LICENSE.txt | https://raw.githubusercontent.com/amerkoleci/Vortice.Windows/6f1300554c4894171dff06d89d139c5a39a741ad/LICENSE |
| vortice-mathematics-2.0.0-LICENSE.txt | https://raw.githubusercontent.com/amerkoleci/Vortice.Mathematics/af5830a6de7a1699e658ed07233fff013b0a8a72/LICENSE |
| sharpgen-2.4.2-beta-LICENSE.txt | https://raw.githubusercontent.com/SharpGenTools/SharpGenTools/6990bcafe124a4c22515ad19cee5a081da8db67b/LICENSE.txt |
| wpf-10.0.11-THIRD-PARTY-NOTICES.txt | https://raw.githubusercontent.com/dotnet/wpf/v10.0.11/THIRD-PARTY-NOTICES.TXT |
| winforms-10.0.11-THIRD-PARTY-NOTICES.txt | https://raw.githubusercontent.com/dotnet/winforms/v10.0.11/THIRD-PARTY-NOTICES.TXT |

When updating dependency versions, refresh the corresponding notices and hash
manifest. The packaging script rejects an unreviewed .NET runtime version
whose matching license has not been staged.

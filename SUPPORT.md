# ByteRescue Support

**GitHub Repository:** [https://github.com/CodingJeffRoblox/ByteRescue](https://github.com/CodingJeffRoblox/ByteRescue)

## Getting Help

### Documentation
- **README.md** - Main documentation, features, and getting started guide
- **CONTRIBUTING.md** - For contributors and developers
- This file (SUPPORT.md) - Support and troubleshooting information
- **GitHub Repository** - [https://github.com/CodingJeffRoblox/ByteRescue](https://github.com/CodingJeffRoblox/ByteRescue)

### Common Issues

#### Installation Issues
**Problem**: "Module not found" errors when running `python app.py`
- **Solution**: Ensure you've installed dependencies: `python -m pip install -r requirements.txt`
- **Solution**: Check you're using Python 3.7 or later
- **Solution**: Try creating a virtual environment first

#### Permission Issues
**Problem**: "Access denied" when trying to access physical drives
- **Solution**: Run ByteRescue as Administrator
- **Solution**: On Windows, right-click the Command Prompt/PowerShell and select "Run as administrator"
- **Solution**: Some drives may be locked by the OS or other applications

#### GUI Won't Start
**Problem**: Double-clicking ByteRescue.bat doesn't open the window
- **Solution**: Run `python app.py` from Command Prompt to see error messages
- **Solution**: Check that Python is installed and in your PATH
- **Solution**: Verify dependencies are installed

#### Recovery Fails
**Problem**: Recovery scan completes but no files are found
- **Solution**: The drive may have been TRIM'd (SSD) - data may be permanently gone
- **Solution**: Files may have been overwritten by new data
- **Solution**: Try the Hex Viewer to manually inspect the drive
- **Solution**: Check that you're scanning the correct drive/partition

#### Drive Not Detected
**Problem**: Physical drive doesn't appear in the drive list
- **Solution**: Run as Administrator
- **Solution**: Ensure the drive is properly connected
- **Solution**: Check Disk Management to see if Windows detects the drive
- **Solution**: Some external drives may need to be connected before starting ByteRescue

### Crash and Error Handling

ByteRescue 0.1.2 includes improved crash handling:
- Startup errors are displayed in error dialogs
- File access errors show readable messages
- The GUI remains responsive during scans
- Recovery errors are caught and reported

If you encounter a crash:
1. Note the error message displayed
2. Check the Command Prompt/PowerShell window for additional details
3. Try restarting the application
4. Ensure you have adequate disk space and permissions

### Performance Tips

#### Large Drives
- Scanning large drives (1TB+) can take considerable time
- Consider scanning specific folders instead of entire drives
- Use the Hex Viewer for targeted inspection
- Close other applications to free up system resources

#### Recovery Speed
- Recovery speed depends on drive speed and interface
- USB 2.0 drives will be slower than USB 3.0/3.1
- SSD recovery is generally faster than HDD
- Signature carving is CPU-intensive

### Data Recovery Best Practices

#### Before You Start
1. **Stop using the drive** - Any write operation may overwrite deleted data
2. **Don't install recovery software on the affected drive** - Install on a different drive
3. **Create a disk image if possible** - Work on the image, not the original
4. **Backup any important data** - If you can still access some files, back them up first

#### During Recovery
1. **Use a separate destination drive** - Never save recovered files to the source drive
2. **Verify file integrity** - Use the Hex Viewer and SHA-256 hashing
3. **Recover most important files first** - Prioritize critical documents and irreplaceable files
4. **Monitor disk space** - Ensure your destination drive has enough space

#### After Recovery
1. **Verify recovered files** - Check that files open correctly
2. **Backup immediately** - Don't lose recovered data again
3. **Consider drive replacement** - If the drive was failing, replace it
4. **Update backups** - Use this as a lesson to maintain regular backups

### When Recovery Isn't Possible

ByteRescue may not be able to recover data in these situations:
- **SSD TRIM**: Modern SSDs permanently erase deleted data
- **Overwritten data**: New data has overwritten the deleted files
- **Physical damage**: Drive hardware failure requires professional services
- **Encrypted drives**: BitLocker or other encryption without the key
- **Severe corruption**: File system damage beyond signature carving
- **RAID arrays**: Complex RAID configurations require specialized tools

For these cases, consider professional data recovery services.

### Reporting Issues

If you encounter a bug or issue not covered here:

1. **Check existing issues** - Look for similar problems in the project's issue tracker
2. **Gather information**:
   - ByteRescue version
   - Windows version
   - Python version
   - Steps to reproduce the issue
   - Error messages (screenshots if possible)
   - Drive type and size
3. **Create a detailed report** - Include all relevant information
4. **Be mindful of sensitive data** - Don't include personal information in bug reports

### Community Support

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Check README.md and other documentation files
- **Open Source**: As an open source project, community contributions are welcome

### Professional Help

For critical data recovery situations:
- Consider professional data recovery services
- These services have clean-room facilities and specialized equipment
- They can handle physical drive damage and complex corruption
- Professional recovery is expensive but may be worth it for critical data

### Safety and Legal

- **Legal ownership**: Only recover data from drives you own or have permission to access
- **Privacy**: Respect privacy laws and data protection regulations
- **Forensics**: For legal cases, consult with digital forensics professionals
- **Chain of custody**: Professional data recovery may be needed for legal evidence

## Contact

For questions, issues, or contributions, please use the project's GitHub repository:
- **Main Repository:** [https://github.com/CodingJeffRoblox/ByteRescue](https://github.com/CodingJeffRoblox/ByteRescue)
- **Issues:** [https://github.com/CodingJeffRoblox/ByteRescue/issues](https://github.com/CodingJeffRoblox/ByteRescue/issues)
- **Discussions:** [https://github.com/CodingJeffRoblox/ByteRescue/discussions](https://github.com/CodingJeffRoblox/ByteRescue/discussions)

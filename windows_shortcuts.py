import struct


def read_shortcut_path(shortcut_filename):
    """
    Read the local target path and additional info of a windows shortcut file (.lnk)
    :rtype: (str, dict[str,str])
    """
    # Based on http://stackoverflow.com/a/28952464/1119602
    #
    # For more info on the format see
    # https://github.com/libyal/liblnk/blob/master/documentation/Windows%20Shortcut%20File%20(LNK)%20format.asciidoc

    with open(shortcut_filename, 'rb') as stream:
        content = stream.read()
        # skip first 20 bytes (HeaderSize and LinkCLSID)
        # read the LinkFlags structure (4 bytes)
        lflags = struct.unpack('I', content[0x14:0x18])[0]

        has_description = (lflags & 0x4) == 0x4
        has_relative_path = (lflags & 0x8) == 0x8
        has_working_dir = (lflags & 0x10) == 0x10
        has_command_line_arguments = (lflags & 0x20) == 0x20
        is_unicode = (lflags & 0x80) == 0x80

        position = 0x18
        # if the HasLinkTargetIDList bit is set then skip the stored IDList
        # structure and header
        if (lflags & 0x01) == 1:
            position = struct.unpack('H', content[0x4C:0x4E])[0] + 0x4E

        last_pos = position
        position += 0x04
        # get how long the file information is (LinkInfoSize)
        length = struct.unpack('I', content[last_pos:position])[0]

        location_info_end = last_pos + length
        # skip 12 bytes (LinkInfoHeaderSize, LinkInfoFlags and VolumeIDOffset)
        position += 0x0C
        # go to the LocalBasePath position
        local_base_path_pos = struct.unpack('I', content[position:position+0x04])[0]
        common_path_pos = struct.unpack('I', content[position+8:position+12])[0]
        position = last_pos + local_base_path_pos
        common_position = last_pos + common_path_pos
        # read the string at the given position of the determined length
        raw_local_path_content = content[position:location_info_end]
        raw_common_content = content[common_position:location_info_end]
        common_content = raw_common_content.split(b'\x00', 1)[0]
        local_path_content = raw_local_path_content.split(b'\x00', 1)[0]

        local_full_path = local_path_content + common_content
        target = local_full_path.decode("windows-1252")

        additional_strings_present = []
        if has_description:
            additional_strings_present.append("description")
        if has_relative_path:
            additional_strings_present.append("relative_path")
        if has_working_dir:
            additional_strings_present.append("working_dir")
        if has_command_line_arguments:
            additional_strings_present.append("command_line_arguments")

        additional_data = {}

        pos = last_pos + length
        for data_string_name in additional_strings_present:
            num_chars = struct.unpack('H', content[pos:pos+2])[0]
            num_bytes = num_chars * (2 if is_unicode else 1)
            end = pos + 2 + num_bytes
            data_bytes = content[pos+2:end]
            data_string = data_bytes.decode("utf-16le" if is_unicode else "windows-1252")
            additional_data[data_string_name] = data_string
            pos = end

        return target, additional_data